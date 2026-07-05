import os
import json
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow

def main():
    parser = argparse.ArgumentParser(description="YouTube OAuth2 Authorizer")
    parser.add_argument("--channel", type=str, required=True, help="ID channel (contoh: logikastoik)")
    args = parser.parse_args()
    channel_id = args.channel.lower()

    print("====================================================")
    print(f"YouTube OAuth2 Authorizer untuk Channel: {channel_id}")
    print("====================================================")
    print("Skrip ini akan membuka browser lokal Anda untuk memberikan")
    print("izin akses upload video ke channel YouTube Anda.")
    print("====================================================\n")
    
    secret_file = "client_secret.json"
    if not os.path.exists(secret_file):
        print(f"Eror: Berkas '{secret_file}' tidak ditemukan!")
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

    # SCOPES yang dibutuhkan untuk upload video, membaca statistik, dan komentar
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly"
    ]
    
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
    
    output_file = f"youtube_credentials_{channel_id}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cred_data, f, indent=4, ensure_ascii=False)
        
    print("\n✅ Otorisasi Sukses!")
    print(f"💾 Kredensial penting tersimpan di: {output_file}")
    print("\n⚠️ PERINGATAN KEAMANAN:")
    print(f"1. Jangan pernah memasukkan (commit) berkas '{output_file}' atau 'client_secret.json' ke GitHub!")
    print(f"2. Buka berkas '{output_file}', salin seluruh isinya, dan masukkan ke")
    print(f"   GitHub Secrets repositori Anda dengan nama rahasia 'YOUTUBE_CREDENTIALS_{channel_id.upper()}'.")

if __name__ == "__main__":
    main()
