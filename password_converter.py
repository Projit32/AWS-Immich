import hmac
import hashlib
import base64


def generate_smtp_password(secret_key, region):
    # Constants strictly required by AWS for SES SMTP conversion
    DATE = "11111111"
    SERVICE = "ses"
    TERMINAL = "aws4_request"
    MESSAGE = "SendRawEmail"
    VERSION = 0x04

    # 1. Sign the initial key
    signature = hmac.new(
        key=("AWS4" + secret_key).encode('utf-8'),
        msg=DATE.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()

    # 2. Sequentially sign the region, service, terminal, and message
    signature = hmac.new(signature, region.encode('utf-8'), hashlib.sha256).digest()
    signature = hmac.new(signature, SERVICE.encode('utf-8'), hashlib.sha256).digest()
    signature = hmac.new(signature, TERMINAL.encode('utf-8'), hashlib.sha256).digest()
    signature = hmac.new(signature, MESSAGE.encode('utf-8'), hashlib.sha256).digest()

    # 3. Prepend the version byte and encode the final hash to Base64
    signature_and_version = bytes([VERSION]) + signature
    smtp_password = base64.b64encode(signature_and_version).decode('utf-8')

    return smtp_password


# --- Run the Script ---
if __name__ == "__main__":
    print("AWS SES SMTP Password Converter")
    print("-" * 31)

    user_secret = input("Enter your IAM Secret Access Key: ").strip()
    user_region = input("Enter your AWS Region (e.g., us-east-1): ").strip()

    if len(user_secret) != 40:
        print("\n[Warning] AWS Secret Keys are normally exactly 40 characters long.")

    try:
        final_password = generate_smtp_password(user_secret, user_region)
        print("\n✅ Conversion Successful!")
        print("Copy the password below and paste it into Immich:\n")
        print(final_password)
        print()
    except Exception as e:
        print(f"\n❌ Error: {e}")