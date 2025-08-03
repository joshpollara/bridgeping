#!/usr/bin/env python3
import secrets

print("Add this to your .env file:")
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")