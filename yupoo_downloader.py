#!/usr/bin/env python3
"""
Yupoo → Google Drive Downloader
Raspa imagens de álbuns da Yupoo e envia direto para o Google Drive,
organizando em pastas por álbum.
"""

import os
import sys
import time
import json
import re
import requests
from urllib.parse import urljoin, urlparse, urlencode
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# ─── Cores para o terminal ──────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}[OK]{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}[WARN]{RESET}  {msg}")
def err(msg):   print(f"  {RED}[ERR]{RESET}  {msg}")
def info(msg):  print(f"  {CYAN}>>> {RESET}  {msg}")
def dim(msg):   print(f"     {GRAY}{msg}{RESET}")

# ─── Constantes ─────────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# ─── Autenticação Google Drive ───────────────────────────────────────────────
def setup_env_credentials():
    """Converte variáveis de ambiente em arquivos para compatibilidade com a lib do Google"""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    token_json = os.environ.get("GOOGLE_TOKEN")
    
    # Diagnóstico inicial silencioso
    if not creds_json and not token_json:
        dim("Nenhuma credencial detectada via variáveis de ambiente.")
        return

    def clean_json(content):
        if not content: return None
        content = content.strip()
        # Remove aspas extras que podem vir de gerenciadores de env vars
        if (content.startswith("'") and content.endswith("'")) or \
           (content.startswith('"') and content.endswith('"')):
            content = content[1:-1].strip()
        return content

    if creds_json:
        clean_creds = clean_json(creds_json)
        try:
            # Tenta validar se é JSON mesmo
            json.loads(clean_creds)
            with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                f.write(clean_creds)
            ok(f"Arquivo '{CREDENTIALS_FILE}' configurado via variável de ambiente.")
        except Exception as e:
            err(f"Conteúdo em GOOGLE_CREDENTIALS não é um JSON válido: {e}")
        
    if token_json:
        clean_token = clean_json(token_json)
        try:
            json.loads(clean_token)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(clean_token)
            ok(f"Arquivo '{TOKEN_FILE}' configurado via variável de ambiente.")
        except Exception as e:
            err(f"Conteúdo em GOOGLE_TOKEN não é um JSON válido: {e}")

def authenticate_google():
    """Autentica via OAuth2 e retorna o servio do Drive."""
    setup_env_credentials()
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            info("Renovando token de acesso...")
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                err(f"Arquivo '{CREDENTIALS_FILE}' não encontrado!")
                warn("Nota: Verifique se a variável GOOGLE_CREDENTIALS está definida no Docker/Coolify.")
                print(f"""
  {BOLD}Como resolver:{RESET}
  1. Se estiver rodando LOCAL: 
     Certifique-se que o arquivo {BOLD}credentials.json{RESET} está na mesma pasta.
  
  2. Se estiver rodando no DOCKER/VPS/COOLIFY:
     Defina a variável de ambiente {BOLD}GOOGLE_CREDENTIALS{RESET} com o conteúdo 
     INTEIRO do arquivo JSON das suas credenciais do Google.
""")
                sys.exit(1)

            info("Abrindo navegador para autenticação Google...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        ok("Token salvo em token.json (próximas execuções não precisam autenticar)")

    return build("drive", "v3", credentials=creds)

# ─── Google Drive helpers ─────────────────────────────────────────────────────
def escape_q(value):
    """Escapa aspas simples para consultas do Google Drive."""
    return value.replace("'", "\\'")

def drive_find_or_create_folder(service, name, parent_id=None):
    """Busca pasta pelo nome ou cria se não existir."""
    safe_name = escape_q(name)
    query = f"name='{safe_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]

    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]

def drive_list_files(service, folder_id):
    """Retorna um set com todos os nomes de arquivos em uma pasta."""
    files_in_folder = set()
    page_token = None
    
    while True:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, 
            fields="nextPageToken, files(name)",
            pageToken=page_token
        ).execute()
        
        for f in results.get("files", []):
            files_in_folder.add(f["name"])
            
        page_token = results.get("nextPageToken")
        if not page_token:
            break
            
    return files_in_folder

def drive_file_exists(service, name, folder_id):
    """[LEGACY] Verifica se um arquivo já existe na pasta (Chamada individual lenta)."""
    safe_name = escape_q(name)
    query = f"name='{safe_name}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    return len(results.get("files", [])) > 0

def drive_upload(service, image_bytes, filename, folder_id, mime_type="image/jpeg"):
    """Faz upload de bytes de imagem para o Drive."""
    meta = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=mime_type, resumable=True)
    file = service.files().create(body=meta, media_body=media, fields="id").execute()
    return file.get("id")

# ─── Scraping da Yupoo ────────────────────────────────────────────────────────
def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def parse_album_page(session, url):
    """Extrai imagens e nome do álbum de uma página da Yupoo."""
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        err(f"Falha ao acessar {url}: {e}")
        return [], "erro", []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Nome do álbum
    title_el = (
        soup.find("h1", class_=re.compile("album", re.I)) or
        soup.find("title") or
        soup.find("h1")
    )
    album_name = title_el.get_text(strip=True) if title_el else "album_" + str(int(time.time()))
    album_name = re.sub(r'[\\/*?:"<>|]', "_", album_name)[:80].strip()

    # Tenta focar no container principal do álbum para evitar logos no cabeçalho/rodapé
    container = soup.find("div", class_="showalbum__children") or soup
    
    # Coleta imagens
    images = []
    seen = set()

    # Estratégia 1: Extração via JSON.parse (mais completa se disponível)
    for script in soup.find_all("script"):
        text = script.string or ""
        if "JSON.parse" in text:
            try:
                match = re.search(r'JSON\.parse\("(.+?)"\)', text)
                if match:
                    raw_json = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
                    data = json.loads(raw_json)
                    photos = data.get("album", {}).get("photos", [])
                    for p in photos:
                        url = p.get("origin_src") or p.get("big_src") or p.get("src")
                        title = p.get("title", "") or ""
                        if not url: continue
                        if url.startswith("//"): url = "https:" + url

                        if re.search(r'[A-Z]\d+[A-Z]\d+', title.upper()):
                            is_trash = any(x in title.lower() or x in url.lower() for x in ("chart", "logo", "size", "banner", "static"))
                            if not is_trash:
                                clean = re.sub(r'\?.*$', '', url)
                                # Extrai ID único da foto (ex: d223daef) do caminho da URL
                                photo_id = clean.split("/")[-2] if "/" in clean else clean
                                if photo_id not in seen:
                                    seen.add(photo_id)
                                    images.append(clean)
            except: pass

    # Estratégia 2: Extração via Atributos de Imagem
    for img in soup.find_all("img"):
        url = img.get("data-origin-src") or img.get("data-big-src") or img.get("data-src") or img.get("src")
        title = img.get("title") or img.get("alt") or ""
        
        if not url: continue
        if url.startswith("//"): url = "https:" + url
        
        if re.search(r'[A-Z]\d+[A-Z]\d+', title.upper()):
            is_trash = any(x in title.lower() or x in url.lower() for x in ("chart", "logo", "size", "banner", "static"))
            if not is_trash:
                clean = re.sub(r'\?.*$', '', url)
                # Extrai ID único da foto (ex: d223daef)
                photo_id = clean.split("/")[-2] if "/" in clean else clean
                if photo_id not in seen:
                    seen.add(photo_id)
                    images.append(clean)

    # Paginação: busca links de próxima página
    next_pages = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r'[?&]page=\d+', href) or "next" in (a.get("class") or []) or a.get_text(strip=True).lower() in ("next", "próximo", ">", "»"):
            full = urljoin(url, href)
            if full != url and full not in next_pages:
                next_pages.append(full)

    return images, album_name, next_pages

def get_albums_from_catalog(session, catalog_url):
    """
    Se o link for uma página de catálogo (lista de álbuns), 
    percorre todas as páginas e coleta os links de cada álbum individual.
    """
    album_urls = []
    visited = set()
    queue = [catalog_url]
    
    info(f"Vasculhando catálogo: {catalog_url}")
    
    while queue:
        url = queue.pop(0)
        if url in visited: continue
        visited.add(url)
        
        # Tenta acessar com retentativas
        max_retries = 3
        resp = None
        for attempt in range(max_retries):
            try:
                resp = session.get(url, timeout=60)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    warn(f"Tentativa {attempt+1} falhou para {url}. Tentando novamente em 2s...")
                    time.sleep(2)
                else:
                    err(f"Falha definitiva ao acessar {url}: {e}")
                    continue
        
        if not resp: continue
            
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Encontra links de álbuns
        # Yupoo usa classes como album__main ou album3__main
        found_on_page = 0
        for a in soup.find_all("a", class_=re.compile(r'album\d*__main')):
            href = a.get("href")
            if href:
                full_url = urljoin(url, href)
                # Garante que é um link de álbum (contém /albums/ e um ID no final)
                if "/albums/" in full_url and re.search(r'/\d+(\?|$)', full_url):
                    if full_url not in album_urls:
                        album_urls.append(full_url)
                        found_on_page += 1
        
        if found_on_page > 0:
            dim(f"Encontrados {found_on_page} álbuns em {url}")
            
        # Paginação do catálogo
        for a in soup.find_all("a", class_=re.compile(r'pagination__button')):
            # Procura por "próxima", "next", ">" ou título "página seguinte"
            text = a.get_text(strip=True).lower()
            title = (a.get("title") or "").lower()
            if any(x in text for x in (">", "next", "próximo", "seguinte")) or "seguinte" in title:
                href = a.get("href")
                if href:
                    full_next = urljoin(url, href)
                    if full_next not in visited:
                        queue.append(full_next)
        
        time.sleep(0.5)
        
    ok(f"Total de {len(album_urls)} álbuns encontrados na loja.")
    return album_urls

def detect_url_type(url):
    """Detecta se a URL é um álbum individual ou um catálogo/loja."""
    # Um álbum individual geralmente termina com o ID numérico
    # Ex: .../albums/12345678
    if re.search(r'/albums/\d+(\?|$)', url):
        return "album"
    return "catalog"

def scrape_all_pages(session, start_url):
    """Percorre todas as páginas de um álbum e coleta todas as imagens."""
    all_images = []
    visited = set()
    queue = [start_url]
    album_name = None

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        dim(f"Página: {url}")
        images, name, next_pages = parse_album_page(session, url)

        if album_name is None:
            album_name = name

        new = [i for i in images if i not in all_images]
        all_images.extend(new)
        dim(f"{len(images)} imagens encontradas nesta página (acumulado: {len(all_images)})")

        for p in next_pages:
            if p not in visited:
                queue.append(p)

        time.sleep(0.8)  # respeita o servidor

    return all_images, album_name or "album"

def detect_mime(url, data):
    """Detecta o tipo MIME pela extensão ou magic bytes."""
    if url.lower().endswith(".png") or data[:4] == b'\x89PNG':
        return "image/png"
    if url.lower().endswith(".webp"):
        return "image/webp"
    if url.lower().endswith(".gif"):
        return "image/gif"
    return "image/jpeg"

def safe_filename(url, index):
    """Gera um nome de arquivo seguro a partir da URL."""
    name = urlparse(url).path.split("/")[-1]
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    if not name or "." not in name:
        name = f"img_{index:04d}.jpg"
    return name

# ─── Pipeline principal ────────────────────────────────────────────────────────
def process_album(session, service, album_url, root_folder_id, opts):
    print(f"\n{BOLD}{CYAN}*** Álbum: {album_url} ***{RESET}")

    images, album_name = scrape_all_pages(session, album_url)[:2]

    if not images:
        warn("Nenhuma imagem encontrada. O álbum pode ser privado ou protegido.")
        return {"total": 0, "sent": 0, "skipped": 0, "failed": 0}

    ok(f"Total de imagens encontradas: {len(images)}")

    # Pasta de destino
    if opts["subfolder_per_album"]:
        folder_id = drive_find_or_create_folder(service, album_name, root_folder_id)
        ok(f"Pasta no Drive: '{album_name}'")
    else:
        folder_id = root_folder_id

    stats = {"total": len(images), "sent": 0, "skipped": 0, "failed": 0}

    # Busca arquivos existentes de uma vez só (Otimização)
    existing_files = set()
    if opts["skip_existing"]:
        try:
            existing_files = drive_list_files(service, folder_id)
        except Exception as e:
            warn(f"Falha ao listar arquivos da pasta: {e}. Prosseguindo sem cache local.")

    for i, img_url in enumerate(images, 1):
        filename = safe_filename(img_url, i)

        if opts["skip_existing"] and filename in existing_files:
            # dim(f"[{i}/{len(images)}] Já existe: {filename}") # Otimizado: silenciar para logs mais limpos
            stats["skipped"] += 1
            continue

        try:
            # Importante: o Yupoo exige que o Referer seja o próprio site para liberar a imagem (Erro 567)
            session.headers.update({"Referer": album_url})
            
            resp = session.get(img_url, timeout=30)
            resp.raise_for_status()
            data = resp.content
            mime = detect_mime(img_url, data)

            drive_upload(service, data, filename, folder_id, mime)
            ok(f"[{i}/{len(images)}] Enviada: {filename} ({len(data)//1024} KB)")
            stats["sent"] += 1

        except Exception as e:
            err(f"[{i}/{len(images)}] Falha: {filename} — {e}")
            stats["failed"] += 1

        time.sleep(opts["delay"])

    # Se todas as imagens do álbum foram puladas, marca como completamente pulado
    if stats["skipped"] == stats["total"] and stats["total"] > 0:
        stats["completely_skipped"] = True
        dim(f"Álbum já estava 100% sincronizado ({stats['total']} imagens).")

    return stats

def print_summary(all_stats):
    total  = sum(s["total"]   for s in all_stats)
    sent   = sum(s["sent"]    for s in all_stats)
    skip   = sum(s["skipped"] for s in all_stats)
    failed = sum(s["failed"]  for s in all_stats)

    print(f"""
{BOLD}{'─'*50}
  Resumo final
{'─'*50}{RESET}
  {GREEN}Enviadas:  {sent}{RESET}
  {YELLOW}Ignoradas: {skip}{RESET}
  {RED}Falhas:    {failed}{RESET}
  {GRAY}Total:     {total}{RESET}
{'─'*50}
""")

def load_config():
    """Carrega configurações do arquivo config.json se existir."""
    if os.path.exists("config.json"):
        with open("config.json") as f:
            return json.load(f)
    return {}

# ─── Entrada principal ─────────────────────────────────────────────────────────
def main():
    print(f"""
{BOLD}{CYAN}
  ██╗   ██╗██╗   ██╗██████╗  ██████╗  ██████╗
  ╚██╗ ██╔╝██║   ██║██╔══██╗██╔═══██╗██╔═══██╗
   ╚████╔╝ ██║   ██║██████╔╝██║   ██║██║   ██║
    ╚██╔╝  ██║   ██║██╔═══╝ ██║   ██║██║   ██║
     ██║   ╚██████╔╝██║     ╚██████╔╝╚██████╔╝
     ╚═╝    ╚═════╝ ╚═╝      ╚═════╝  ╚═════╝
  -- Google Drive Downloader
{RESET}""")

    config = load_config()

    # ── URLs dos álbuns ──────────────────────────────────────────────────────
    urls = config.get("urls", [])
    if not urls:
        print(f"  {BOLD}Cole os links dos álbuns ou da LOJA da Yupoo (um por linha).{RESET}")
        print(f"  {GRAY}Deixe uma linha em branco para terminar:{RESET}\n")
        while True:
            line = input("  URL: ").strip()
            if not line:
                break
            urls.append(line)

    if not urls:
        err("Nenhuma URL informada. Encerrando.")
        sys.exit(1)

    # ── Expansão de Catálogos ────────────────────────────────────────────────
    session = get_session()
    final_album_list = []
    
    for url in urls:
        if detect_url_type(url) == "catalog":
            info(f"Detectada URL de Catálogo/Loja: {url}")
            store_albums = get_albums_from_catalog(session, url)
            final_album_list.extend(store_albums)
        else:
            final_album_list.append(url)
            
    if not final_album_list:
        err("Nenhum álbum encontrado para processar.")
        sys.exit(1)
        
    urls = final_album_list

    # ── Opções ───────────────────────────────────────────────────────────────
    opts = {
        "root_folder": config.get("root_folder", "Yupoo Downloads"),
        "subfolder_per_album": config.get("subfolder_per_album", True),
        "skip_existing": config.get("skip_existing", True),
        "delay": config.get("delay_seconds", 0.5),
        "stop_after_consecutive_skipped": config.get("stop_after_consecutive_skipped", 10),
    }

    print(f"""
  {BOLD}Configuração:{RESET}
  • Pasta raiz no Drive:   {opts['root_folder']}
  • Subpasta por álbum:    {'sim' if opts['subfolder_per_album'] else 'não'}
  • Pular já enviadas:     {'sim' if opts['skip_existing'] else 'não'}
  • Parar após sync:       {opts['stop_after_consecutive_skipped']} álbuns (0=desativado)
  • Intervalo entre imgs:  {opts['delay']}s
  • Álbuns a processar:    {len(urls)}
""")

    # ── Autenticação ─────────────────────────────────────────────────────────
    info("Conectando ao Google Drive...")
    service = authenticate_google()
    ok("Google Drive conectado!")

    # ── Pasta raiz ───────────────────────────────────────────────────────────
    root_id = drive_find_or_create_folder(service, opts["root_folder"])
    ok(f"Pasta raiz: '{opts['root_folder']}'")

    # ── Processa cada álbum ──────────────────────────────────────────────────
    # Já temos a sessão instanciada acima na expansão
    all_stats = []
    consecutive_skipped = 0

    for i, url in enumerate(urls, 1):
        s = process_album(session, service, url, root_id, opts)
        all_stats.append(s)

        if s.get("completely_skipped"):
            consecutive_skipped += 1
        else:
            consecutive_skipped = 0

        # Lógica de parada antecipada (Early Exit)
        limit = opts.get("stop_after_consecutive_skipped", 0)
        if limit > 0 and consecutive_skipped >= limit:
            print(f"\n{BOLD}{YELLOW}>>> Limite de álbuns já sincronizados atingido ({limit}).{RESET}")
            print(f"{YELLOW}>>> Assumindo que o restante da loja já foi processado anteriormente.{RESET}")
            break

    print_summary(all_stats)

if __name__ == "__main__":
    main()
