# DWG para GLB

Aplicacao web simples para enviar um arquivo `.dwg`, converte-lo por meio da
Aspose.CAD Cloud API e baixar o resultado `.glb`.

## Requisitos

- Python 3.11 ou superior
- Uma conta Aspose Cloud com `Client ID` e `Client Secret`

Crie as credenciais no [painel da Aspose Cloud](https://dashboard.aspose.cloud/).
Os arquivos enviados para conversao passam pela infraestrutura da Aspose.

## Executar localmente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Defina as variaveis da `.env` na sessao (ou no seu gerenciador de segredos):

```powershell
$env:ASPOSE_CLIENT_ID="seu_client_id"
$env:ASPOSE_CLIENT_SECRET="seu_client_secret"
uvicorn app.main:app --reload
```

Abra [http://localhost:8000](http://localhost:8000).

> O servidor le variaveis de ambiente. O arquivo `.env` e apenas um modelo e
> nao e carregado automaticamente para evitar comportamento oculto em producao.

## Testes

```powershell
pytest
```

Os testes nao enviam arquivos para a Aspose e nao consomem a API.

## Docker

```powershell
docker build -t dwg-to-glb .
docker run --rm -p 8000:8000 `
  -e ASPOSE_CLIENT_ID="seu_client_id" `
  -e ASPOSE_CLIENT_SECRET="seu_client_secret" `
  dwg-to-glb
```

## GitHub Pages

A interface estatica e publicada automaticamente pelo workflow
`.github/workflows/pages.yml`. O GitHub Pages nao executa o backend Python.

Depois de hospedar o backend em um servico HTTPS, crie no repositorio a
variavel de Actions `PUBLIC_API_BASE_URL` com a origem do backend, por exemplo:

```text
https://conversor-dwg.exemplo.com
```

No backend, defina `ALLOWED_ORIGINS=https://cleitonpn.github.io`. Nunca coloque
`ASPOSE_CLIENT_SECRET` no JavaScript, no GitHub Pages ou em variaveis publicas.

## Backend no Render

O arquivo `render.yaml` define um Web Service Docker chamado
`conversor-dwg-api`. No painel do Render, crie um novo Blueprint a partir deste
repositorio e informe `ASPOSE_CLIENT_ID` e `ASPOSE_CLIENT_SECRET` quando
solicitado. O health check usa `/api/health`.

Depois que o deploy terminar, copie a URL `https://...onrender.com` e salve-a
como a variavel de Actions `PUBLIC_API_BASE_URL` no repositorio GitHub. Execute
novamente o workflow `publicar GitHub Pages` para conectar a interface ao
backend.

## Limites conhecidos

- Um DWG 2D produz geometria essencialmente plana no GLB.
- Fontes, objetos proxy, materiais e entidades proprietarias podem ser
  simplificados pelo conversor.
- O limite de upload padrao e 100 MB e pode ser alterado por `MAX_UPLOAD_MB`.

## Licenca

MIT

