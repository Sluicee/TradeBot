"""
Генератор примера запроса для проверки в браузере
"""
import hmac
import hashlib
import time
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def generate_request_example():
    """Генерирует пример запроса для проверки в браузере"""
    
    # Получаем API ключи
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    
    print("=== BYBIT API REQUEST EXAMPLE ===")
    print()
    
    if not api_key or not api_secret:
        print("ERROR: API keys not set in .env")
        return
    
    # Параметры запроса
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    params = {"accountType": "UNIFIED"}
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    
    # Генерируем подпись
    signature_string = timestamp + api_key + recv_window + query_string
    signature = hmac.new(
        api_secret.encode('utf-8'),
        signature_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print("1. REQUEST DETAILS:")
    print(f"   URL: https://api.bybit.com/v5/account/wallet-balance")
    print(f"   Method: GET")
    print(f"   Query String: {query_string}")
    print()
    
    print("2. HEADERS:")
    print(f"   X-BAPI-API-KEY: {api_key}")
    print(f"   X-BAPI-SIGN: {signature}")
    print(f"   X-BAPI-TIMESTAMP: {timestamp}")
    print(f"   X-BAPI-RECV-WINDOW: {recv_window}")
    print(f"   Content-Type: application/json")
    print()
    
    print("3. SIGNATURE GENERATION:")
    print(f"   Timestamp: {timestamp}")
    print(f"   API Key: {api_key}")
    print(f"   Recv Window: {recv_window}")
    print(f"   Query String: {query_string}")
    print(f"   Signature String: {signature_string}")
    print(f"   Generated Signature: {signature}")
    print()
    
    print("4. CURL COMMAND:")
    curl_cmd = f'''curl -X GET "https://api.bybit.com/v5/account/wallet-balance?{query_string}" \\
  -H "X-BAPI-API-KEY: {api_key}" \\
  -H "X-BAPI-SIGN: {signature}" \\
  -H "X-BAPI-TIMESTAMP: {timestamp}" \\
  -H "X-BAPI-RECV-WINDOW: {recv_window}" \\
  -H "Content-Type: application/json"'''
    print(curl_cmd)
    print()
    
    print("5. BROWSER TEST:")
    print("   Copy this URL to browser (with headers from Postman/Insomnia):")
    print(f"   https://api.bybit.com/v5/account/wallet-balance?{query_string}")
    print()
    
    print("6. POSTMAN/INSOMNIA SETUP:")
    print("   Method: GET")
    print(f"   URL: https://api.bybit.com/v5/account/wallet-balance?{query_string}")
    print("   Headers:")
    print(f"     X-BAPI-API-KEY: {api_key}")
    print(f"     X-BAPI-SIGN: {signature}")
    print(f"     X-BAPI-TIMESTAMP: {timestamp}")
    print(f"     X-BAPI-RECV-WINDOW: {recv_window}")
    print(f"     Content-Type: application/json")
    print()
    
    print("7. EXPECTED RESPONSE:")
    print("   If API key is valid:")
    print('   {"retCode": 0, "retMsg": "OK", "result": {"list": [...]}}')
    print()
    print("   If API key is invalid:")
    print('   {"retCode": 10003, "retMsg": "API key is invalid.", "result": {}}')
    print()
    
    print("8. TROUBLESHOOTING:")
    print("   - Check if API key has 'Read' permissions")
    print("   - Check if API key is not expired")
    print("   - Check if using correct environment (mainnet vs testnet)")
    print("   - Verify signature generation matches Bybit documentation")

if __name__ == "__main__":
    generate_request_example()
