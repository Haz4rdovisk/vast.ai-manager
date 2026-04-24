
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import ConfigStore
from app.services.vast_service import VastService
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

    vast = VastService(config.api_key)
    try:
        keys = vast.list_ssh_keys()
        print(f"\n--- Registered Keys on Vast ---")
        match_found = False
        for k in keys:
            print(f"ID: {k.id}, Label: {k.label}, Key Prefix: {k.public_key[:30]}...")
            if pub and pub.strip().split()[:2] == k.public_key.strip().split()[:2]:
                print(f"  ==> MATCH FOUND! ID: {k.id}")
                match_found = True
        
        if not match_found:
            print("\n!!! NO MATCHING KEY FOUND ON VAST.AI !!!")

        instances = vast.list_instances()
        target_iid = 35259078
        target = next((i for i in instances if i.id == target_iid), None)
        
        if target:
            print(f"\n--- Target Instance #{target_iid} ---")
            print(f"State: {target.state}")
            print(f"SSH Host: {target.ssh_host}:{target.ssh_port}")
            # The API doesn't usually return WHICH key was used during rent in the simple list, 
            # but we can see what's in authorized_keys if we could connect... which we can't.
        else:
            print(f"\nInstance #{target_iid} not found in the list.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_ssh()
