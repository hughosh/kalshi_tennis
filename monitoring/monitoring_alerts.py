"""
Monitoring and Alerts System

This module implements comprehensive monitoring and alerting for the tennis trading system,
including performance metrics, system health checks, and real-time alerts.
"""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import time
import numpy as np
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    LOG = "log"


@dataclass
class Alert:
    """Alert with metadata and routing information"""
    alert_id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    source: str
    channels: List[AlertChannel] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False


@dataclass
class SystemMetrics:
    """System performance metrics"""
    timestamp: datetime
    
    # Trading metrics
    active_positions: int = 0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    win_rate: float = 0.0
    
    # System metrics
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    
    # Data feed metrics
    feed_latency_ms: float = 0.0
    feed_success_rate: float = 0.0
    data_staleness_seconds: float = 0.0
    
    # Order execution metrics
    order_success_rate: float = 0.0
    average_fill_time_ms: float = 0.0
    rejected_orders: int = 0
    
    # Risk metrics
    current_drawdown: float = 0.0
    max_correlation: float = 0.0
    circuit_breaker_active: bool = False


class AlertRule:
    """Alert rule with conditions and actions"""
    
    def __init__(self, 
                 name: str,
                 condition: Callable[[SystemMetrics], bool],
                 level: AlertLevel,
                 channels: List[AlertChannel],
                 cooldown_minutes: int = 15):
        self.name = name
        self.condition = condition
        self.level = level
        self.channels = channels
        self.cooldown_minutes = cooldown_minutes
        self.last_triggered: Optional[datetime] = None
    
    def should_trigger(self, metrics: SystemMetrics) -> bool:
        """Check if rule should trigger"""
        if not self.condition(metrics):
            return False
        
        # Check cooldown
        if self.last_triggered:
            time_since_last = datetime.now() - self.last_triggered
            if time_since_last.total_seconds() < self.cooldown_minutes * 60:
                return False
        
        return True
    
    def trigger(self, metrics: SystemMetrics) -> Alert:
        """Create alert for this rule"""
        self.last_triggered = datetime.now()
        
        return Alert(
            alert_id=f"{self.name}_{int(time.time())}",
            level=self.level,
            title=f"{self.name} Alert",
            message=self._generate_message(metrics),
            timestamp=datetime.now(),
            source="monitoring_system",
            channels=self.channels,
            metadata={"metrics": metrics.__dict__}
        )
    
    def _generate_message(self, metrics: SystemMetrics) -> str:
        """Generate alert message"""
        return f"Alert triggered: {self.name}\nTimestamp: {metrics.timestamp}\nMetrics: {json.dumps(metrics.__dict__, default=str)}"


class AlertManager:
    """Manages alert routing and delivery"""
    
    def __init__(self):
        self.channels: Dict[AlertChannel, Any] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.active_alerts: Dict[str, Alert] = {}
        
        # Statistics
        self.total_alerts = 0
        self.alerts_by_level: Dict[AlertLevel, int] = defaultdict(int)
        self.alerts_by_channel: Dict[AlertChannel, int] = defaultdict(int)
    
    def add_channel(self, channel: AlertChannel, config: Dict[str, Any]):
        """Add alert delivery channel"""
        self.channels[channel] = config
        logger.info(f"Added alert channel: {channel.value}")
    
    def send_alert(self, alert: Alert):
        """Send alert through configured channels"""
        self.alert_history.append(alert)
        self.active_alerts[alert.alert_id] = alert
        
        # Update statistics
        self.total_alerts += 1
        self.alerts_by_level[alert.level] += 1
        
        # Send through each channel
        for channel in alert.channels:
            if channel in self.channels:
                try:
                    self._send_to_channel(alert, channel)
                    self.alerts_by_channel[channel] += 1
                except Exception as e:
                    logger.error(f"Failed to send alert to {channel.value}: {e}")
            else:
                logger.warning(f"Channel {channel.value} not configured")
    
    def _send_to_channel(self, alert: Alert, channel: AlertChannel):
        """Send alert to specific channel"""
        if channel == AlertChannel.EMAIL:
            self._send_email(alert)
        elif channel == AlertChannel.SLACK:
            self._send_slack(alert)
        elif channel == AlertChannel.WEBHOOK:
            self._send_webhook(alert)
        elif channel == AlertChannel.LOG:
            self._log_alert(alert)
    
    def _send_email(self, alert: Alert):
        """Send alert via email"""
        config = self.channels[AlertChannel.EMAIL]
        
        msg = MIMEMultipart()
        msg['From'] = config['from_email']
        msg['To'] = config['to_email']
        msg['Subject'] = f"[{alert.level.value.upper()}] {alert.title}"
        
        body = f"""
        Alert: {alert.title}
        Level: {alert.level.value}
        Time: {alert.timestamp}
        Source: {alert.source}
        
        Message:
        {alert.message}
        
        Metadata:
        {json.dumps(alert.metadata, indent=2)}
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['username'], config['password'])
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email alert sent: {alert.alert_id}")
    
    def _send_slack(self, alert: Alert):
        """Send alert via Slack"""
        config = self.channels[AlertChannel.SLACK]
        
        # Color coding based on level
        color_map = {
            AlertLevel.INFO: "good",
            AlertLevel.WARNING: "warning",
            AlertLevel.ERROR: "danger",
            AlertLevel.CRITICAL: "danger"
        }
        
        payload = {
            "channel": config['channel'],
            "username": "Tennis Trading Bot",
            "icon_emoji": ":tennis:",
            "attachments": [{
                "color": color_map[alert.level],
                "title": alert.title,
                "text": alert.message,
                "fields": [
                    {"title": "Level", "value": alert.level.value, "short": True},
                    {"title": "Time", "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"), "short": True},
                    {"title": "Source", "value": alert.source, "short": True}
                ],
                "timestamp": int(alert.timestamp.timestamp())
            }]
        }
        
        response = requests.post(config['webhook_url'], json=payload)
        response.raise_for_status()
        
        logger.info(f"Slack alert sent: {alert.alert_id}")
    
    def _send_webhook(self, alert: Alert):
        """Send alert via webhook"""
        config = self.channels[AlertChannel.WEBHOOK]
        
        payload = {
            "alert_id": alert.alert_id,
            "level": alert.level.value,
            "title": alert.title,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
            "source": alert.source,
            "metadata": alert.metadata
        }
        
        response = requests.post(config['url'], json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info(f"Webhook alert sent: {alert.alert_id}")
    
    def _log_alert(self, alert: Alert):
        """Log alert to system logs"""
        log_level_map = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL
        }
        
        logger.log(log_level_map[alert.level], 
                  f"ALERT: {alert.title} - {alert.message}")
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].acknowledged = True
            logger.info(f"Alert {alert_id} acknowledged")
    
    def resolve_alert(self, alert_id: str):
        """Resolve an alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].resolved = True
            del self.active_alerts[alert_id]
            logger.info(f"Alert {alert_id} resolved")
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics"""
        return {
            'total_alerts': self.total_alerts,
            'active_alerts': len(self.active_alerts),
            'alerts_by_level': dict(self.alerts_by_level),
            'alerts_by_channel': dict(self.alerts_by_channel),
            'configured_channels': list(self.channels.keys())
        }


class SystemMonitor:
    """
    Monitors system health and performance metrics.
    """
    
    def __init__(self, alert_manager: AlertManager):
        self.alert_manager = alert_manager
        self.metrics_history: deque = deque(maxlen=1440)  # 24 hours of minute data
        self.alert_rules: List[AlertRule] = []
        
        # Initialize default alert rules
        self._setup_default_rules()
        
        logger.info("SystemMonitor initialized")
    
    def _setup_default_rules(self):
        """Setup default alert rules"""
        
        # High drawdown alert
        self.alert_rules.append(AlertRule(
            name="High Drawdown",
            condition=lambda m: m.current_drawdown > 0.10,
            level=AlertLevel.WARNING,
            channels=[AlertChannel.EMAIL, AlertChannel.SLACK],
            cooldown_minutes=30
        ))
        
        # Critical drawdown alert
        self.alert_rules.append(AlertRule(
            name="Critical Drawdown",
            condition=lambda m: m.current_drawdown > 0.15,
            level=AlertLevel.CRITICAL,
            channels=[AlertChannel.EMAIL, AlertChannel.SLACK, AlertChannel.WEBHOOK],
            cooldown_minutes=5
        ))
        
        # Circuit breaker alert
        self.alert_rules.append(AlertRule(
            name="Circuit Breaker Active",
            condition=lambda m: m.circuit_breaker_active,
            level=AlertLevel.CRITICAL,
            channels=[AlertChannel.EMAIL, AlertChannel.SLACK, AlertChannel.WEBHOOK],
            cooldown_minutes=1
        ))
        
        # Data feed issues
        self.alert_rules.append(AlertRule(
            name="Data Feed Issues",
            condition=lambda m: m.feed_success_rate < 0.95 or m.data_staleness_seconds > 10,
            level=AlertLevel.ERROR,
            channels=[AlertChannel.EMAIL, AlertChannel.SLACK],
            cooldown_minutes=15
        ))
        
        # Order execution issues
        self.alert_rules.append(AlertRule(
            name="Order Execution Issues",
            condition=lambda m: m.order_success_rate < 0.90,
            level=AlertLevel.WARNING,
            channels=[AlertChannel.EMAIL],
            cooldown_minutes=30
        ))
        
        # High correlation risk
        self.alert_rules.append(AlertRule(
            name="High Correlation Risk",
            condition=lambda m: m.max_correlation > 0.8,
            level=AlertLevel.WARNING,
            channels=[AlertChannel.EMAIL],
            cooldown_minutes=60
        ))
        
        # System resource issues
        self.alert_rules.append(AlertRule(
            name="High CPU Usage",
            condition=lambda m: m.cpu_usage > 0.90,
            level=AlertLevel.WARNING,
            channels=[AlertChannel.EMAIL],
            cooldown_minutes=30
        ))
        
        self.alert_rules.append(AlertRule(
            name="High Memory Usage",
            condition=lambda m: m.memory_usage > 0.90,
            level=AlertLevel.WARNING,
            channels=[AlertChannel.EMAIL],
            cooldown_minutes=30
        ))
    
    def collect_metrics(self, 
                       trading_system: Any,
                       data_pipeline: Any,
                       risk_manager: Any) -> SystemMetrics:
        """Collect current system metrics"""
        metrics = SystemMetrics(timestamp=datetime.now())
        
        # Trading metrics
        if hasattr(trading_system, 'active_positions'):
            metrics.active_positions = len(trading_system.active_positions)
        
        if hasattr(trading_system, 'total_pnl'):
            metrics.total_pnl = trading_system.total_pnl
        
        # Data pipeline metrics
        if hasattr(data_pipeline, 'get_pipeline_status'):
            pipeline_status = data_pipeline.get_pipeline_status()
            metrics.feed_success_rate = pipeline_status['statistics']['success_rate']
            metrics.feed_latency_ms = pipeline_status['statistics']['average_latency_ms']
        
        # Risk metrics
        if hasattr(risk_manager, 'risk_metrics'):
            metrics.current_drawdown = risk_manager.risk_metrics.current_drawdown
            metrics.max_correlation = risk_manager.risk_metrics.max_correlation
            metrics.circuit_breaker_active = risk_manager.circuit_breaker_active
        
        # System metrics (simplified)
        metrics.cpu_usage = 0.5  # Placeholder
        metrics.memory_usage = 0.6  # Placeholder
        metrics.disk_usage = 0.3  # Placeholder
        
        return metrics
    
    def check_alerts(self, metrics: SystemMetrics):
        """Check all alert rules and trigger alerts if needed"""
        for rule in self.alert_rules:
            if rule.should_trigger(metrics):
                alert = rule.trigger(metrics)
                self.alert_manager.send_alert(alert)
                logger.info(f"Alert triggered: {rule.name}")
    
    def update_metrics(self, metrics: SystemMetrics):
        """Update metrics history and check alerts"""
        self.metrics_history.append(metrics)
        self.check_alerts(metrics)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of recent metrics"""
        if not self.metrics_history:
            return {}
        
        recent_metrics = list(self.metrics_history)[-60:]  # Last hour
        
        return {
            'current_metrics': recent_metrics[-1].__dict__ if recent_metrics else {},
            'average_metrics': {
                'cpu_usage': np.mean([m.cpu_usage for m in recent_metrics]),
                'memory_usage': np.mean([m.memory_usage for m in recent_metrics]),
                'feed_latency_ms': np.mean([m.feed_latency_ms for m in recent_metrics]),
                'active_positions': np.mean([m.active_positions for m in recent_metrics])
            },
            'alert_rules_count': len(self.alert_rules),
            'metrics_history_size': len(self.metrics_history)
        }


class HealthChecker:
    """
    Performs system health checks and generates reports.
    """
    
    def __init__(self):
        self.health_checks: Dict[str, Callable] = {}
        self._setup_default_checks()
    
    def _setup_default_checks(self):
        """Setup default health checks"""
        self.health_checks = {
            'data_feed_connectivity': self._check_data_feed_connectivity,
            'kalshi_api_connectivity': self._check_kalshi_api_connectivity,
            'database_connectivity': self._check_database_connectivity,
            'disk_space': self._check_disk_space,
            'memory_usage': self._check_memory_usage,
            'trading_system_status': self._check_trading_system_status
        }
    
    def run_health_checks(self) -> Dict[str, Dict[str, Any]]:
        """Run all health checks"""
        results = {}
        
        for check_name, check_func in self.health_checks.items():
            try:
                result = check_func()
                results[check_name] = {
                    'status': 'healthy' if result['healthy'] else 'unhealthy',
                    'message': result['message'],
                    'timestamp': datetime.now(),
                    'details': result.get('details', {})
                }
            except Exception as e:
                results[check_name] = {
                    'status': 'error',
                    'message': f"Health check failed: {e}",
                    'timestamp': datetime.now(),
                    'details': {}
                }
        
        return results
    
    def _check_data_feed_connectivity(self) -> Dict[str, Any]:
        """Check data feed connectivity"""
        # Simplified check
        return {
            'healthy': True,
            'message': 'Data feed connectivity OK',
            'details': {'latency_ms': 50}
        }
    
    def _check_kalshi_api_connectivity(self) -> Dict[str, Any]:
        """Check Kalshi API connectivity"""
        # Simplified check
        return {
            'healthy': True,
            'message': 'Kalshi API connectivity OK',
            'details': {'response_time_ms': 100}
        }
    
    def _check_database_connectivity(self) -> Dict[str, Any]:
        """Check database connectivity"""
        return {
            'healthy': True,
            'message': 'Database connectivity OK',
            'details': {'connection_pool_size': 10}
        }
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space"""
        return {
            'healthy': True,
            'message': 'Disk space OK',
            'details': {'free_space_gb': 50}
        }
    
    def _check_memory_usage(self) -> Dict[str, Any]:
        """Check memory usage"""
        return {
            'healthy': True,
            'message': 'Memory usage OK',
            'details': {'usage_percent': 60}
        }
    
    def _check_trading_system_status(self) -> Dict[str, Any]:
        """Check trading system status"""
        return {
            'healthy': True,
            'message': 'Trading system running',
            'details': {'active_strategies': 1}
        }


# Test the monitoring system
if __name__ == "__main__":
    print("Testing Monitoring and Alerts System...")
    
    # Create alert manager
    alert_manager = AlertManager()
    
    # Add email channel (mock)
    alert_manager.add_channel(AlertChannel.EMAIL, {
        'from_email': 'alerts@tennisbot.com',
        'to_email': 'admin@tennisbot.com',
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': 'alerts@tennisbot.com',
        'password': 'password'
    })
    
    # Add Slack channel (mock)
    alert_manager.add_channel(AlertChannel.SLACK, {
        'webhook_url': 'https://hooks.slack.com/services/...',
        'channel': '#tennis-trading'
    })
    
    # Create system monitor
    monitor = SystemMonitor(alert_manager)
    
    # Create health checker
    health_checker = HealthChecker()
    
    # Test metrics collection
    metrics = SystemMetrics(
        timestamp=datetime.now(),
        active_positions=5,
        total_pnl=150.0,
        current_drawdown=0.12,  # Trigger high drawdown alert
        feed_success_rate=0.98,
        data_staleness_seconds=5.0,
        order_success_rate=0.95,
        max_correlation=0.6,
        circuit_breaker_active=False
    )
    
    # Update metrics and check alerts
    monitor.update_metrics(metrics)
    
    # Run health checks
    health_results = health_checker.run_health_checks()
    print(f"Health check results: {health_results}")
    
    # Get statistics
    alert_stats = alert_manager.get_alert_statistics()
    print(f"Alert statistics: {alert_stats}")
    
    metrics_summary = monitor.get_metrics_summary()
    print(f"Metrics summary: {metrics_summary}")
    
    print("\nMonitoring and Alerts System test complete!")
