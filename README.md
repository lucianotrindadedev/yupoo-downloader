# Yupoo → Google Drive Downloader

Baixa imagens de álbuns da Yupoo e envia direto para o Google Drive,
organizando em subpastas por álbum.

---

## Requisitos

- Python 3.8 ou superior
- Conta Google com Google Drive

---

## Instalação (faça só uma vez)

### 1. Instale as dependências

Abra o terminal na pasta do projeto e execute:

```bash
pip install -r requirements.txt
```

No Windows, se o comando acima não funcionar:
```bash
py -m pip install -r requirements.txt
```

---

### 2. Configure as credenciais do Google Drive

1. Acesse: https://console.cloud.google.com
2. Crie um projeto novo (botão no topo) ou selecione um existente
3. No menu lateral: **APIs e Serviços → Biblioteca**
4. Busque **"Google Drive API"** e clique em **Ativar**
5. No menu lateral: **APIs e Serviços → Credenciais**
6. Clique em **Criar credenciais → ID do cliente OAuth 2.0**
7. Tipo de aplicativo: **Aplicativo para computador**
8. Dê um nome qualquer (ex: "Yupoo Downloader") e clique em Criar
9. Clique no ícone de download (⬇) para baixar o JSON
10. Renomeie o arquivo baixado para `credentials.json`
11. Coloque o `credentials.json` na mesma pasta que o script

> Na primeira execução, uma janela do navegador abrirá pedindo autorização.
> Após autorizar, um arquivo `token.json` é criado automaticamente —
> nas próximas execuções não precisará autenticar novamente.

---

## Configuração (opcional)

Edite o arquivo `config.json` para definir os links e opções:

```json
{
  "urls": [
    "https://storenome.x.yupoo.com/albums/12345"
  ],
  "root_folder": "Yupoo Downloads",
  "subfolder_per_album": true,
  "skip_existing": true,
  "delay_seconds": 0.5
}
```

| Campo | Descrição | Padrão |
|---|---|---|
| `urls` | Lista de links de álbuns para baixar | (pergunta ao rodar) |
| `root_folder` | Nome da pasta raiz no Drive | `"Yupoo Downloads"` |
| `subfolder_per_album` | Cria subpasta com nome do álbum | `true` |
| `skip_existing` | Pula imagens já enviadas | `true` |
| `delay_seconds` | Pausa entre downloads (respeita o servidor) | `0.5` |

Se o `config.json` não tiver URLs, o script pedirá os links interativamente ao rodar.

---

## Uso

### Modo interativo (sem config.json)
```bash
python yupoo_downloader.py
```
O script pedirá os links no terminal.

### Modo com config.json
1. Edite o `config.json` com os links desejados
2. Execute:
```bash
python yupoo_downloader.py
```

---

## Resultado no Google Drive

```
Yupoo Downloads/
├── Nome do Álbum 1/
│   ├── img_0001.jpg
│   ├── img_0002.jpg
│   └── ...
├── Nome do Álbum 2/
│   ├── img_0001.jpg
│   └── ...
```

---

## Dicas e solução de problemas

**"Nenhuma imagem encontrada"**
→ O álbum pode ser privado, ou a Yupoo mudou a estrutura HTML. Verifique se o link abre no navegador sem login.

**Erro de autenticação Google**
→ Delete o arquivo `token.json` e execute novamente para reautenticar.

**Downloads lentos**
→ Aumente o `delay_seconds` no config.json para não sobrecarregar o servidor.

**Imagens duplicadas**
→ Mantenha `skip_existing: true` — o script checa se o arquivo já existe no Drive antes de enviar.
