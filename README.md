# DWG 3D para GLB

Aplicacao web para converter arquivos `.dwg` com geometria 3D em `.glb` sem
usar uma API de conversao externa. O processamento acontece no proprio backend:

1. o [LibreDWG](https://www.gnu.org/software/libredwg/) le o DWG e gera um DXF temporario;
2. o `ezdxf` expande blocos e transforma malhas, faces e curvas 3D;
3. a aplicacao normaliza as unidades para metros, converte de Z-up para Y-up,
   centraliza o modelo e grava um GLB 2.0.

Os arquivos temporarios sao removidos ao final da requisicao.

## Executar com Docker

O Dockerfile compila e instala a versao fixada do LibreDWG. Nenhuma chave ou
conta externa e necessaria.

```powershell
docker build -t dwg-to-glb .
docker run --rm -p 8000:8000 dwg-to-glb
```

Abra [http://localhost:8000](http://localhost:8000).

## Desenvolvimento sem Docker

Requer Python 3.11 ou superior e o executavel `dwg2dxf` do LibreDWG no `PATH`.
Tambem e possivel informar o caminho completo em `LIBREDWG_DWG2DXF`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:LIBREDWG_DWG2DXF="C:\caminho\dwg2dxf.exe"
uvicorn app.main:app --reload
```

## Testes

```powershell
pytest
```

## GitHub Pages e Render

A interface estatica e publicada pelo workflow `.github/workflows/pages.yml`.
Como o GitHub Pages nao executa Python, a conversao roda no Web Service Docker
do Render definido em `render.yaml`. O frontend usa por padrao:

```text
https://conversor-dwg-api.onrender.com
```

Se o endereco mudar, atualize no repositorio a variavel de Actions
`PUBLIC_API_BASE_URL` e publique o Pages novamente. O backend aceita os ajustes:

- `MAX_UPLOAD_MB` (padrao: `100`)
- `ALLOWED_ORIGINS` (origens separadas por virgula)
- `LIBREDWG_DWG2DXF` (opcional, caminho alternativo do executavel)

## Geometria suportada

- malhas, polyfaces, `3DFACE`, `SOLID` e `TRACE`;
- linhas, polilinhas, arcos, circulos, elipses e splines 3D;
- blocos aninhados, incluindo translacao, rotacao e escala.

O conversor nao inventa volume para desenhos 2D. Solidos ACIS (`3DSOLID`,
`BODY`, `REGION` e `SURFACE`) exigem tessellacao proprietaria. Quando o arquivo
tambem possui malhas, a geometria de malha real e convertida; quando possui
somente ACIS, a API recusa a conversao com uma mensagem clara, em vez de gerar
um GLB vazio. Para incluir esses solidos, converta-os para `MESH`/`3DFACE` no CAD
antes do upload.

Materiais, texturas, fontes e objetos proxy proprietarios podem nao estar
presentes no resultado.

## Licenca

MIT
