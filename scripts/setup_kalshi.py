#!/usr/bin/env python3
"""
Kalshi RSA Key Setup Script

This script helps you set up your Kalshi RSA secret key for the tennis trading system.
"""

import os
import sys

def setup_kalshi_credentials():
    """Set up Kalshi credentials"""
    print("🔑 Kalshi RSA Key Setup")
    print("=" * 30)
    
    # Check if files already exist
    if os.path.exists('kalshi_secret_key.txt'):
        print("✅ kalshi_secret_key.txt already exists")
    else:
        print("❌ kalshi_secret_key.txt not found")
        print("\nTo set up your RSA key:")
        print("1. Copy the contents of your RSA secret key file")
        print("2. Run: echo 'your_rsa_key_content' > kalshi_secret_key.txt")
        print("3. Or manually create the file and paste your key")
    
    if os.path.exists('kalshi_username.txt'):
        print("✅ kalshi_username.txt already exists")
    else:
        print("❌ kalshi_username.txt not found")
        print("\nTo set up your username:")
        print("1. Run: echo 'your_email@example.com' > kalshi_username.txt")
        print("2. Replace with your actual Kalshi account email")
    
    print("\n📁 Required files:")
    print("- kalshi_secret_key.txt (your RSA private key)")
    print("- kalshi_username.txt (your Kalshi email)")
    
    print("\n🚀 Once files are created, run:")
    print("python live_tennis_trading.py")

def create_example_files():
    """Create example files with instructions"""
    
    # Create example secret key file
    with open('kalshi_secret_key.txt.example', 'w') as f:
        f.write("""-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
(your actual RSA private key goes here)
...
-----END RSA PRIVATE KEY-----""")
    
    # Create example username file
    with open('kalshi_username.txt.example', 'w') as f:
        f.write("your_email@example.com")
    
    print("📝 Created example files:")
    print("- kalshi_secret_key.txt.example")
    print("- kalshi_username.txt.example")
    print("\nCopy these files and replace with your actual credentials:")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-examples":
        create_example_files()
    else:
        setup_kalshi_credentials()
