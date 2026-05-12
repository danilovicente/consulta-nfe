# Consulta NF-e

Ferramenta em Python para consultar Notas Fiscais Eletrônicas (NF-e) emitidas contra o seu CNPJ, utilizando certificado digital A1 (.pfx/.p12).

A ferramenta utiliza o serviço de **Distribuição de DF-e** da SEFAZ (Ambiente Nacional) para buscar os documentos fiscais.

## Requisitos

- Python 3.10+
- Certificado digital A1 (arquivo `.pfx` ou `.p12`)
- CNPJ cadastrado na SEFAZ

## Instalação

```bash
# Clone o repositório
git clone https://github.com/danilovicente/consulta-nfe.git
cd consulta-nfe

# Instale as dependências
pip install -e .
```

Ou usando `uv`:

```bash
uv pip install -e .
```

## Uso

### Buscar todas as NF-e

Busca todas as NF-e emitidas contra o seu CNPJ:

```bash
consulta-nfe buscar \
    --certificado /caminho/do/certificado.pfx \
    --cnpj 12345678000199 \
    --uf SP \
    --ambiente producao
```

A senha do certificado será solicitada de forma segura no terminal.

### Buscar a partir de um NSU específico

Para continuar uma busca de onde parou:

```bash
consulta-nfe buscar \
    --certificado /caminho/do/certificado.pfx \
    --cnpj 12345678000199 \
    --nsu-inicial 000000000012345
```

### Consultar NF-e por chave de acesso

```bash
consulta-nfe consultar-chave \
    --certificado /caminho/do/certificado.pfx \
    --cnpj 12345678000199 \
    --chave 35210612345678000199550010000000011234567890
```

### Exportar resultados

#### JSON

```bash
consulta-nfe buscar \
    --certificado /caminho/do/certificado.pfx \
    --cnpj 12345678000199 \
    --exportar-json notas.json
```

#### XMLs individuais

```bash
consulta-nfe buscar \
    --certificado /caminho/do/certificado.pfx \
    --cnpj 12345678000199 \
    --exportar-xml ./xmls/
```

### Informações do certificado

```bash
consulta-nfe info-certificado --certificado /caminho/do/certificado.pfx
```

## Opções

### Comando `buscar`

| Opção | Descrição | Padrão |
|---|---|---|
| `--certificado`, `-c` | Caminho do certificado .pfx/.p12 | (obrigatório) |
| `--senha`, `-s` | Senha do certificado | (solicitada) |
| `--cnpj` | CNPJ do destinatário | (obrigatório) |
| `--uf` | UF do autor | SP |
| `--ambiente`, `-a` | `producao` ou `homologacao` | producao |
| `--nsu-inicial` | NSU inicial para busca | 0 |
| `--max-consultas` | Máximo de consultas paginadas | 50 |
| `--exportar-json` | Arquivo JSON de saída | - |
| `--exportar-xml` | Diretório para XMLs | - |

### Comando `consultar-chave`

| Opção | Descrição | Padrão |
|---|---|---|
| `--certificado`, `-c` | Caminho do certificado .pfx/.p12 | (obrigatório) |
| `--senha`, `-s` | Senha do certificado | (solicitada) |
| `--cnpj` | CNPJ do destinatário | (obrigatório) |
| `--chave` | Chave de acesso (44 dígitos) | (obrigatório) |
| `--uf` | UF do autor | SP |
| `--ambiente`, `-a` | `producao` ou `homologacao` | producao |
| `--exportar-xml` | Diretório para exportar o XML | - |

## Ambientes

- **Produção**: Consulta NF-e reais no ambiente de produção da SEFAZ
- **Homologação**: Ambiente de teste da SEFAZ (para desenvolvimento)

## Como funciona

1. O certificado digital A1 (.pfx/.p12) é carregado e a chave privada é extraída
2. Uma requisição SOAP é enviada ao serviço de Distribuição de DF-e da SEFAZ (Ambiente Nacional)
3. A autenticação é feita via mTLS (mutual TLS) usando o certificado digital
4. Os documentos retornados são descomprimidos (gzip + base64) e parseados
5. Os resultados são exibidos em uma tabela formatada ou exportados em JSON/XML

## Tipos de documentos retornados

- **resNFe**: Resumo de NF-e (dados básicos como emitente, valor, data)
- **procNFe**: NF-e completa com todos os detalhes
- **resEvento**: Resumo de eventos (cancelamento, carta de correção, etc.)

## Códigos de status comuns

| Código | Significado |
|---|---|
| 137 | Nenhum documento localizado |
| 138 | Documentos localizados |
| 656 | Consumo indevido (muitas consultas em pouco tempo) |

## Licença

MIT
