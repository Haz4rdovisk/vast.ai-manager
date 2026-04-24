
import inspect
from vastai import VastAI

def inspect_sdk():
    sdk = VastAI(api_key="test")
    if hasattr(sdk, "attach_ssh"):
        method = sdk.attach_ssh
        print(f"Method: attach_ssh")
        print(f"Signature: {inspect.signature(method)}")
    else:
        print("Method attach_ssh not found in VastAI SDK.")
        # List all methods starting with 'attach'
        attach_methods = [m for m in dir(sdk) if m.startswith("attach")]
        print(f"Attach-related methods: {attach_methods}")

if __name__ == "__main__":
    try:
        inspect_sdk()
    except Exception as e:
        print(f"Error: {e}")
