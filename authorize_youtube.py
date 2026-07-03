import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

def main():
    print("====================================================")
    print("🚀 YouTube OAuth2 Authorizer (Local Script)")
    print("====================================================")
    print("Skrip ini akan membuka browser lokal Anda untuk memberikan")
    print("izin akses upload video ke channel YouTube Anda.")
    print("====================================================\n")
    
    secret_file = "client_secret.json"
    if not os.path.exists(secret_file):
        print(f"❌ Eror: Berkas '{secret_file}' tidak ditemukan!")
        print("\nCara mendapatkan berkas client_secret.json:")
        print("1. Buka Google Cloud Console: https://console.cloud.google.com/")
        print("2. Buat proyek baru, lalu cari dan aktifkan 'YouTube Data API v3'.")
        print("3. Masuk ke menu 'OAuth consent screen', set User Type ke 'External', isi data wajib,")
        print("   lalu pada status Publishing set ke 'Testing' dan tambahkan email Google Anda ke 'Test users'.")
        print("4. Masuk ke menu 'Credentials' -> Klik '+ Create Credentials' -> pilih 'OAuth client ID'.")
        print("5. Pilih Application type: 'Desktop app', isi nama bebas, lalu klik Create.")
        print("6. Klik ikon 'Download JSON' di baris kredensial yang baru dibuat.")
        print("7. Pindahkan berkas tersebut ke folder proyek ini dan ubah namanya menjadi 'client_secret.json'.")
        return

    # SCOPES yang dibutuhkan untuk upload video ke YouTube
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    
    flow = InstalledAppFlow.from_client_secrets_file(secret_file, scopes)
    credentials = flow.run_local_server(port=0)
    
    # Kumpulkan kredensial penting
    cred_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret
    }
    
    output_file = "youtube_credentials.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cred_data, f, indent=4, ensure_ascii=False)
        
    print("\n✅ Otorisasi Sukses!")
    print(f"💾 Kredensial penting tersimpan di: {output_file}")
    print("\n⚠️ PERINGATAN KEAMANAN:")
    print("1. Jangan pernah memasukkan (commit) berkas 'youtube_credentials.json' atau 'client_secret.json' ke GitHub!")
    print("2. Buka berkas 'youtube_credentials.json', salin seluruh isinya, dan masukkan ke")
    print("   GitHub Secrets repositori Anda dengan nama rahasia 'YOUTUBE_CREDENTIALS'.")

if __name__ == "__main__":
    main()
