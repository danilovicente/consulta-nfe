"""Interface de linha de comando para consulta de NF-e."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from consulta_nfe.certificado import CertificadoDigital
from consulta_nfe.sefaz import Ambiente, DocumentoFiscal, SefazClient

console = Console()


def _formatar_cnpj(cnpj: str) -> str:
    """Formata CNPJ com pontuação."""
    cnpj = cnpj.zfill(14)
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


def _formatar_valor(valor: str) -> str:
    """Formata valor monetário."""
    if not valor:
        return "-"
    try:
        v = float(valor)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return valor


def _exibir_tabela(documentos: list[DocumentoFiscal]) -> None:
    """Exibe os documentos em uma tabela formatada."""
    table = Table(title="Notas Fiscais Encontradas", show_lines=True)

    table.add_column("NSU", style="dim", width=8)
    table.add_column("Número", style="cyan", width=10)
    table.add_column("Série", width=5)
    table.add_column("Emitente (CNPJ)", style="green", width=20)
    table.add_column("Razão Social", style="white", max_width=30)
    table.add_column("Valor", style="yellow", justify="right", width=15)
    table.add_column("Data Emissão", style="blue", width=12)
    table.add_column("Tipo", width=8)
    table.add_column("Situação", style="magenta", width=12)

    for doc in documentos:
        if "resEvento" in doc.schema:
            continue

        data_formatada = doc.data_emissao[:10] if doc.data_emissao else "-"
        cnpj_formatado = _formatar_cnpj(doc.cnpj_emitente) if doc.cnpj_emitente else "-"

        table.add_row(
            doc.nsu,
            doc.numero_nf or "-",
            doc.serie or "-",
            cnpj_formatado,
            doc.razao_social_emitente or "-",
            _formatar_valor(doc.valor_total),
            data_formatada,
            doc.tipo_operacao or "-",
            doc.situacao or "-",
        )

    console.print(table)


def _exportar_json(documentos: list[DocumentoFiscal], arquivo: str) -> None:
    """Exporta os documentos em formato JSON."""
    dados = []
    for doc in documentos:
        dados.append({
            "nsu": doc.nsu,
            "chave": doc.chave,
            "numero_nf": doc.numero_nf,
            "serie": doc.serie,
            "cnpj_emitente": doc.cnpj_emitente,
            "razao_social_emitente": doc.razao_social_emitente,
            "valor_total": doc.valor_total,
            "data_emissao": doc.data_emissao,
            "tipo_operacao": doc.tipo_operacao,
            "situacao": doc.situacao,
            "schema": doc.schema,
        })

    Path(arquivo).write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Exportado para {arquivo}[/green]")


def _exportar_xml(documentos: list[DocumentoFiscal], diretorio: str) -> None:
    """Exporta os XMLs individuais dos documentos."""
    dir_path = Path(diretorio)
    dir_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for doc in documentos:
        if doc.xml and doc.chave:
            arquivo = dir_path / f"{doc.chave}.xml"
            arquivo.write_text(doc.xml, encoding="utf-8")
            count += 1
        elif doc.xml:
            arquivo = dir_path / f"nsu_{doc.nsu}.xml"
            arquivo.write_text(doc.xml, encoding="utf-8")
            count += 1

    console.print(f"[green]{count} arquivo(s) XML exportado(s) para {diretorio}/[/green]")


@click.group()
@click.version_option(package_name="consulta-nfe")
def main() -> None:
    """Consulta NF-e - Busca notas fiscais emitidas contra o seu CNPJ."""
    pass


@main.command()
@click.option(
    "--certificado", "-c", required=True,
    type=click.Path(exists=True), help="Caminho do certificado .pfx/.p12",
)
@click.option("--senha", "-s", required=True, prompt=True, hide_input=True, help="Senha do certificado")
@click.option("--cnpj", required=True, help="CNPJ do destinatário")
@click.option("--uf", default="SP", help="UF do autor (padrão: SP)")
@click.option(
    "--ambiente", "-a",
    type=click.Choice(["producao", "homologacao"]), default="producao", help="Ambiente SEFAZ",
)
@click.option("--nsu-inicial", default="0", help="NSU inicial para busca (padrão: 0)")
@click.option("--max-consultas", default=50, help="Máximo de consultas paginadas (padrão: 50)")
@click.option("--exportar-json", "json_file", default=None, help="Exportar resultado em JSON")
@click.option("--exportar-xml", "xml_dir", default=None, help="Diretório para exportar XMLs")
def buscar(
    certificado: str,
    senha: str,
    cnpj: str,
    uf: str,
    ambiente: str,
    nsu_inicial: str,
    max_consultas: int,
    json_file: str | None,
    xml_dir: str | None,
) -> None:
    """Busca todas as NF-e emitidas contra o CNPJ."""
    amb = Ambiente.PRODUCAO if ambiente == "producao" else Ambiente.HOMOLOGACAO

    console.print(Panel(
        f"[bold]Consultando NF-e[/bold]\n"
        f"CNPJ: {_formatar_cnpj(cnpj)}\n"
        f"UF: {uf}\n"
        f"Ambiente: {ambiente.upper()}\n"
        f"NSU Inicial: {nsu_inicial}",
        title="Consulta NF-e",
        border_style="blue",
    ))

    try:
        with console.status("[bold green]Carregando certificado digital..."):
            cert = CertificadoDigital.from_pfx(certificado, senha)
        console.print(f"[green]Certificado carregado:[/green] {cert.subject}")
        console.print(f"[dim]Válido até: {cert.not_valid_after}[/dim]")
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Erro no certificado: {e}[/red]")
        sys.exit(1)

    client = SefazClient(cert, cnpj, uf=uf, ambiente=amb)

    try:
        with console.status("[bold green]Consultando SEFAZ..."):
            resultado = client.consultar_todos(nsu_inicial=nsu_inicial, max_consultas=max_consultas)
    except Exception as e:
        console.print(f"[red]Erro na consulta: {e}[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Status:[/bold] {resultado.status} - {resultado.motivo}")
    console.print(f"[bold]Último NSU:[/bold] {resultado.ultimo_nsu}")
    console.print(f"[bold]Max NSU:[/bold] {resultado.max_nsu}")
    console.print(f"[bold]Documentos:[/bold] {len(resultado.documentos)}\n")

    if resultado.documentos:
        _exibir_tabela(resultado.documentos)

        if json_file:
            _exportar_json(resultado.documentos, json_file)

        if xml_dir:
            _exportar_xml(resultado.documentos, xml_dir)
    else:
        console.print("[yellow]Nenhum documento encontrado.[/yellow]")


@main.command()
@click.option(
    "--certificado", "-c", required=True,
    type=click.Path(exists=True), help="Caminho do certificado .pfx/.p12",
)
@click.option("--senha", "-s", required=True, prompt=True, hide_input=True, help="Senha do certificado")
@click.option("--cnpj", required=True, help="CNPJ do destinatário")
@click.option("--chave", required=True, help="Chave de acesso da NF-e (44 dígitos)")
@click.option("--uf", default="SP", help="UF do autor (padrão: SP)")
@click.option(
    "--ambiente", "-a",
    type=click.Choice(["producao", "homologacao"]), default="producao", help="Ambiente SEFAZ",
)
@click.option("--exportar-xml", "xml_dir", default=None, help="Diretório para exportar o XML")
def consultar_chave(
    certificado: str,
    senha: str,
    cnpj: str,
    chave: str,
    uf: str,
    ambiente: str,
    xml_dir: str | None,
) -> None:
    """Consulta uma NF-e específica pela chave de acesso."""
    amb = Ambiente.PRODUCAO if ambiente == "producao" else Ambiente.HOMOLOGACAO

    try:
        cert = CertificadoDigital.from_pfx(certificado, senha)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Erro no certificado: {e}[/red]")
        sys.exit(1)

    client = SefazClient(cert, cnpj, uf=uf, ambiente=amb)

    try:
        with console.status("[bold green]Consultando SEFAZ..."):
            resultado = client.consultar_por_chave(chave)
    except Exception as e:
        console.print(f"[red]Erro na consulta: {e}[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Status:[/bold] {resultado.status} - {resultado.motivo}")

    if resultado.documentos:
        _exibir_tabela(resultado.documentos)

        if xml_dir:
            _exportar_xml(resultado.documentos, xml_dir)


@main.command()
@click.option(
    "--certificado", "-c", required=True,
    type=click.Path(exists=True), help="Caminho do certificado .pfx/.p12",
)
@click.option("--senha", "-s", required=True, prompt=True, hide_input=True, help="Senha do certificado")
def info_certificado(certificado: str, senha: str) -> None:
    """Exibe informações do certificado digital."""
    try:
        cert = CertificadoDigital.from_pfx(certificado, senha)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Erro: {e}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Subject:[/bold] {cert.subject}\n"
        f"[bold]Issuer:[/bold] {cert.issuer}\n"
        f"[bold]Serial Number:[/bold] {cert.serial_number}\n"
        f"[bold]Válido de:[/bold] {cert.not_valid_before}\n"
        f"[bold]Válido até:[/bold] {cert.not_valid_after}",
        title="Informações do Certificado Digital",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
