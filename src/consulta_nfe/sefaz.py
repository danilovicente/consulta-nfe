"""Cliente SOAP para o serviço de Distribuição de DF-e da SEFAZ."""

from __future__ import annotations

import gzip
from base64 import b64decode
from dataclasses import dataclass, field
from enum import Enum

import requests
from lxml import etree

from consulta_nfe.certificado import CertificadoDigital


class Ambiente(Enum):
    """Ambiente da SEFAZ."""
    PRODUCAO = "1"
    HOMOLOGACAO = "2"


class TipoConsulta(Enum):
    """Tipo de consulta ao serviço de distribuição."""
    POR_NSU = "distNSU"
    POR_CHAVE = "consChNFe"
    POR_NSU_ESPECIFICO = "consNSU"


# Códigos UF
UF_CODES = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23,
    "DF": 53, "ES": 32, "GO": 52, "MA": 21, "MT": 51, "MS": 50,
    "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42,
    "SP": 35, "SE": 28, "TO": 17,
}

# Endpoints do serviço de Distribuição de DF-e (Ambiente Nacional)
ENDPOINTS = {
    Ambiente.PRODUCAO: "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    Ambiente.HOMOLOGACAO: "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}

# Namespaces
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_NFE_DIST = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
VERSAO_DIST = "1.01"


@dataclass
class DocumentoFiscal:
    """Representa um documento fiscal retornado pela consulta."""

    nsu: str
    schema: str
    xml: str
    chave: str = ""
    cnpj_emitente: str = ""
    razao_social_emitente: str = ""
    valor_total: str = ""
    data_emissao: str = ""
    numero_nf: str = ""
    serie: str = ""
    tipo_operacao: str = ""  # 0=Entrada, 1=Saída
    situacao: str = ""


@dataclass
class ResultadoConsulta:
    """Resultado da consulta de distribuição de DF-e."""

    status: str
    motivo: str
    ultimo_nsu: str = ""
    max_nsu: str = ""
    documentos: list[DocumentoFiscal] = field(default_factory=list)


class SefazClient:
    """Cliente para o serviço de Distribuição de DF-e da SEFAZ."""

    def __init__(
        self,
        certificado: CertificadoDigital,
        cnpj: str,
        uf: str = "SP",
        ambiente: Ambiente = Ambiente.PRODUCAO,
    ):
        self.certificado = certificado
        self.cnpj = self._limpar_cnpj(cnpj)
        self.uf = uf.upper()
        self.cuf = UF_CODES.get(self.uf, 35)
        self.ambiente = ambiente
        self.endpoint = ENDPOINTS[ambiente]

    @staticmethod
    def _limpar_cnpj(cnpj: str) -> str:
        """Remove caracteres não numéricos do CNPJ."""
        return "".join(c for c in cnpj if c.isdigit())

    def _build_soap_envelope(self, body_xml: str) -> str:
        """Constrói o envelope SOAP para a requisição."""
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="{NS_SOAP}">
    <soap12:Header/>
    <soap12:Body>
        <nfeDistDFeInteresse xmlns="{NS_NFE_DIST}">
            <nfeDadosMsg>
                {body_xml}
            </nfeDadosMsg>
        </nfeDistDFeInteresse>
    </soap12:Body>
</soap12:Envelope>"""

    def _build_dist_nsu(self, ultimo_nsu: str = "0") -> str:
        """Constrói XML para consulta por NSU (todas as NF-e a partir de um NSU)."""
        nsu_formatado = ultimo_nsu.zfill(15)
        return f"""<distDFeInt xmlns="{NS_NFE}" versao="{VERSAO_DIST}">
    <tpAmb>{self.ambiente.value}</tpAmb>
    <cUFAutor>{self.cuf}</cUFAutor>
    <CNPJ>{self.cnpj}</CNPJ>
    <distNSU>
        <ultNSU>{nsu_formatado}</ultNSU>
    </distNSU>
</distDFeInt>"""

    def _build_cons_chave(self, chave: str) -> str:
        """Constrói XML para consulta por chave de acesso."""
        return f"""<distDFeInt xmlns="{NS_NFE}" versao="{VERSAO_DIST}">
    <tpAmb>{self.ambiente.value}</tpAmb>
    <cUFAutor>{self.cuf}</cUFAutor>
    <CNPJ>{self.cnpj}</CNPJ>
    <consChNFe>
        <chNFe>{chave}</chNFe>
    </consChNFe>
</distDFeInt>"""

    def _build_cons_nsu(self, nsu: str) -> str:
        """Constrói XML para consulta de um NSU específico."""
        nsu_formatado = nsu.zfill(15)
        return f"""<distDFeInt xmlns="{NS_NFE}" versao="{VERSAO_DIST}">
    <tpAmb>{self.ambiente.value}</tpAmb>
    <cUFAutor>{self.cuf}</cUFAutor>
    <CNPJ>{self.cnpj}</CNPJ>
    <consNSU>
        <NSU>{nsu_formatado}</NSU>
    </consNSU>
</distDFeInt>"""

    def _enviar_request(self, xml_body: str) -> str:
        """Envia requisição SOAP para a SEFAZ usando o certificado digital."""
        envelope = self._build_soap_envelope(xml_body)

        cert_path, key_path = self.certificado.to_temp_files()

        try:
            headers = {
                "Content-Type": "application/soap+xml; charset=utf-8",
            }

            response = requests.post(
                self.endpoint,
                data=envelope.encode("utf-8"),
                headers=headers,
                cert=(cert_path, key_path),
                timeout=60,
            )
            response.raise_for_status()
            return response.text
        finally:
            self.certificado.cleanup_temp_files(cert_path, key_path)

    def _parse_response(self, response_xml: str) -> ResultadoConsulta:
        """Faz parse da resposta SOAP da SEFAZ."""
        try:
            root = etree.fromstring(response_xml.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            return ResultadoConsulta(status="999", motivo=f"Erro ao parsear resposta: {e}")

        ns = {
            "soap": NS_SOAP,
            "nfe": NS_NFE,
            "dist": NS_NFE_DIST,
        }

        ret = root.find(".//nfe:retDistDFeInt", ns)
        if ret is None:
            return ResultadoConsulta(status="999", motivo="Resposta inválida da SEFAZ - retDistDFeInt não encontrado")

        status_el = ret.find("nfe:cStat", ns)
        motivo_el = ret.find("nfe:xMotivo", ns)
        ultimo_nsu_el = ret.find("nfe:ultNSU", ns)
        max_nsu_el = ret.find("nfe:maxNSU", ns)

        status = status_el.text if status_el is not None and status_el.text else "999"
        motivo = motivo_el.text if motivo_el is not None and motivo_el.text else "Sem motivo"
        ultimo_nsu = ultimo_nsu_el.text if ultimo_nsu_el is not None and ultimo_nsu_el.text else "0"
        max_nsu = max_nsu_el.text if max_nsu_el is not None and max_nsu_el.text else "0"

        resultado = ResultadoConsulta(
            status=status,
            motivo=motivo,
            ultimo_nsu=ultimo_nsu,
            max_nsu=max_nsu,
        )

        lote = ret.find("nfe:loteDistDFeInt", ns)
        if lote is not None:
            for doc_zip in lote.findall("nfe:docZip", ns):
                nsu = doc_zip.get("NSU", "")
                schema = doc_zip.get("schema", "")
                xml_comprimido = doc_zip.text

                if xml_comprimido:
                    try:
                        xml_bytes = b64decode(xml_comprimido)
                        xml_descomprimido = gzip.decompress(xml_bytes).decode("utf-8")
                    except Exception:
                        xml_descomprimido = ""

                    doc = self._parse_documento(nsu, schema, xml_descomprimido)
                    resultado.documentos.append(doc)

        return resultado

    def _parse_documento(self, nsu: str, schema: str, xml_content: str) -> DocumentoFiscal:
        """Faz parse de um documento fiscal individual."""
        doc = DocumentoFiscal(nsu=nsu, schema=schema, xml=xml_content)

        if not xml_content:
            return doc

        try:
            root = etree.fromstring(xml_content.encode("utf-8"))
        except etree.XMLSyntaxError:
            return doc

        ns = {"nfe": NS_NFE}

        # Tenta extrair dados de resNFe (resumo) ou nfeProc (NF-e completa)
        if "resNFe" in schema or root.tag.endswith("resNFe"):
            self._parse_res_nfe(root, doc, ns)
        elif "procNFe" in schema or "nfeProc" in schema or root.tag.endswith("nfeProc"):
            self._parse_nfe_proc(root, doc, ns)
        elif "resEvento" in schema or root.tag.endswith("resEvento"):
            self._parse_res_evento(root, doc, ns)

        return doc

    def _parse_res_nfe(self, root: etree._Element, doc: DocumentoFiscal, ns: dict[str, str]) -> None:
        """Parse de resumo de NF-e (resNFe)."""
        chave = root.find("nfe:chNFe", ns)
        if chave is not None and chave.text:
            doc.chave = chave.text

        cnpj = root.find("nfe:CNPJ", ns)
        if cnpj is not None and cnpj.text:
            doc.cnpj_emitente = cnpj.text

        razao = root.find("nfe:xNome", ns)
        if razao is not None and razao.text:
            doc.razao_social_emitente = razao.text

        valor = root.find("nfe:vNF", ns)
        if valor is not None and valor.text:
            doc.valor_total = valor.text

        data = root.find("nfe:dhEmi", ns)
        if data is not None and data.text:
            doc.data_emissao = data.text

        tp_nf = root.find("nfe:tpNF", ns)
        if tp_nf is not None and tp_nf.text:
            doc.tipo_operacao = "Entrada" if tp_nf.text == "0" else "Saída"

        cSit = root.find("nfe:cSitNFe", ns)
        if cSit is not None and cSit.text:
            situacoes = {"1": "Autorizada", "2": "Uso Denegado", "3": "Cancelada"}
            doc.situacao = situacoes.get(cSit.text, cSit.text)

        nNF = root.find("nfe:nNF", ns)
        if nNF is not None and nNF.text:
            doc.numero_nf = nNF.text

        serie = root.find("nfe:serie", ns)
        if serie is not None and serie.text:
            doc.serie = serie.text

    def _parse_nfe_proc(self, root: etree._Element, doc: DocumentoFiscal, ns: dict[str, str]) -> None:
        """Parse de NF-e completa (nfeProc)."""
        inf_nfe = root.find(".//nfe:infNFe", ns)
        if inf_nfe is not None:
            chave = inf_nfe.get("Id", "")
            if chave.startswith("NFe"):
                doc.chave = chave[3:]

        emit = root.find(".//nfe:emit", ns)
        if emit is not None:
            cnpj = emit.find("nfe:CNPJ", ns)
            if cnpj is not None and cnpj.text:
                doc.cnpj_emitente = cnpj.text
            razao = emit.find("nfe:xNome", ns)
            if razao is not None and razao.text:
                doc.razao_social_emitente = razao.text

        total = root.find(".//nfe:total/nfe:ICMSTot/nfe:vNF", ns)
        if total is not None and total.text:
            doc.valor_total = total.text

        ide = root.find(".//nfe:ide", ns)
        if ide is not None:
            data = ide.find("nfe:dhEmi", ns)
            if data is not None and data.text:
                doc.data_emissao = data.text
            nNF = ide.find("nfe:nNF", ns)
            if nNF is not None and nNF.text:
                doc.numero_nf = nNF.text
            serie = ide.find("nfe:serie", ns)
            if serie is not None and serie.text:
                doc.serie = serie.text
            tp_nf = ide.find("nfe:tpNF", ns)
            if tp_nf is not None and tp_nf.text:
                doc.tipo_operacao = "Entrada" if tp_nf.text == "0" else "Saída"

    def _parse_res_evento(self, root: etree._Element, doc: DocumentoFiscal, ns: dict[str, str]) -> None:
        """Parse de resumo de evento (resEvento)."""
        chave = root.find("nfe:chNFe", ns)
        if chave is not None and chave.text:
            doc.chave = chave.text

        cnpj = root.find("nfe:CNPJ", ns)
        if cnpj is not None and cnpj.text:
            doc.cnpj_emitente = cnpj.text

        tp_evento = root.find("nfe:tpEvento", ns)
        if tp_evento is not None and tp_evento.text:
            doc.situacao = f"Evento: {tp_evento.text}"

        desc_evento = root.find("nfe:xEvento", ns)
        if desc_evento is not None and desc_evento.text:
            doc.situacao = desc_evento.text

        data = root.find("nfe:dhEvento", ns)
        if data is not None and data.text:
            doc.data_emissao = data.text

    def consultar_por_nsu(self, ultimo_nsu: str = "0") -> ResultadoConsulta:
        """Consulta NF-e a partir de um NSU.

        Args:
            ultimo_nsu: Último NSU consultado. Use "0" para buscar desde o início.

        Returns:
            ResultadoConsulta com os documentos encontrados
        """
        xml_body = self._build_dist_nsu(ultimo_nsu)
        response = self._enviar_request(xml_body)
        return self._parse_response(response)

    def consultar_por_chave(self, chave: str) -> ResultadoConsulta:
        """Consulta NF-e por chave de acesso.

        Args:
            chave: Chave de acesso da NF-e (44 dígitos)

        Returns:
            ResultadoConsulta com o documento encontrado
        """
        xml_body = self._build_cons_chave(chave)
        response = self._enviar_request(xml_body)
        return self._parse_response(response)

    def consultar_nsu_especifico(self, nsu: str) -> ResultadoConsulta:
        """Consulta um NSU específico.

        Args:
            nsu: NSU do documento a ser consultado

        Returns:
            ResultadoConsulta com o documento encontrado
        """
        xml_body = self._build_cons_nsu(nsu)
        response = self._enviar_request(xml_body)
        return self._parse_response(response)

    def consultar_todos(self, nsu_inicial: str = "0", max_consultas: int = 50) -> ResultadoConsulta:
        """Consulta todas as NF-e disponíveis, paginando automaticamente.

        Args:
            nsu_inicial: NSU inicial para começar a busca
            max_consultas: Número máximo de consultas (para evitar loop infinito)

        Returns:
            ResultadoConsulta consolidado com todos os documentos
        """
        todos_documentos: list[DocumentoFiscal] = []
        ultimo_nsu = nsu_inicial
        consultas = 0

        while consultas < max_consultas:
            resultado = self.consultar_por_nsu(ultimo_nsu)
            consultas += 1

            if resultado.status not in ("137", "138"):
                if not todos_documentos:
                    return resultado
                break

            todos_documentos.extend(resultado.documentos)

            if resultado.ultimo_nsu == resultado.max_nsu:
                ultimo_nsu = resultado.ultimo_nsu
                break

            if resultado.ultimo_nsu == ultimo_nsu:
                break

            ultimo_nsu = resultado.ultimo_nsu

        return ResultadoConsulta(
            status="138" if todos_documentos else resultado.status,
            motivo=f"Consulta finalizada - {len(todos_documentos)} documento(s) encontrado(s)",
            ultimo_nsu=ultimo_nsu,
            max_nsu=resultado.max_nsu if resultado else "0",
            documentos=todos_documentos,
        )
