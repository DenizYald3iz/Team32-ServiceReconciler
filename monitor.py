import requests
import time

def check_service_health(service_url):
    """
    Verilen servisin /health adresine istek atar.
    Cevap alabilirse 'Healthy', alamazsa 'Unhealthy' döner.
    """
    try:
        # 2 saniye içinde cevap gelmezse servis ölü sayılır
        response = requests.get(service_url, timeout=2)
        
        # Eğer 200 OK döndüyse ve JSON içinde 'healthy' varsa
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "healthy":
                return True, "Healthy (Aktif) ✅"
        
        return False, f"Hata: Status Code {response.status_code}"
    
    except requests.exceptions.ConnectionError:
        return False, "Unhealthy (Bağlantı Yok - Ölü) ❌"
    except Exception as e:
        return False, f"Unhealthy (Bilinmeyen Hata: {str(e)})"