
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import ConfigStore
from app.services.rental_service import RentalService
from app.services.ssh_service import SSHService

def debug_ssh():
    store = ConfigStore()
    config = store.load()
    
    print(f"--- Config ---")
    print(f"API Key: {config.api_key[:10]}...")
    print(f"SSH Key Path: {config.ssh_key_path}")
    
    ssh = SSHService(config.ssh_key_path)
    pub = ssh.get_public_key()
    print(f"Local Public Key: {pub[:50]}..." if pub else "Local Public Key: NOT FOUND")
    
    if not config.api_key:
        print("No API Key found.")
        return

    rental = RentalService(config.api_key)
    try:
        keys = rental.list_ssh_keys()
        print(f"\n--- Registered Keys on Vast ---")
        match_found = False
        pub_clean = pub.strip().split()[:2] if pub else []
        
        for k in keys:
            print(f"ID: {k.id}, Label: {k.label}")
            k_clean = k.public_key.strip().split()[:2]
            if pub_clean and pub_clean == k_clean:
                print(f"  ==> MATCH FOUND! ID: {k.id}")
                match_found = True
            else:
                print(f"  Prefix: {k.public_key[:30]}...")
        
        if not match_found:
            print("\n!!! NO MATCHING KEY FOUND ON VAST.AI !!!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_ssh()
