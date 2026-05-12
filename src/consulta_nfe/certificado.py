"""Módulo para manipulação de certificados digitais A1 (.pfx/.p12)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, pkcs12


@dataclass
class CertificadoDigital:
    """Representa um certificado digital A1 extraído de um arquivo .pfx/.p12."""

    cert_pem: bytes
    key_pem: bytes
    subject: str
    issuer: str
    serial_number: int
    not_valid_after: str
    not_valid_before: str

    @classmethod
    def from_pfx(cls, pfx_path: str | Path, senha: str) -> "CertificadoDigital":
        """Carrega um certificado digital a partir de um arquivo .pfx/.p12.

        Args:
            pfx_path: Caminho para o arquivo .pfx ou .p12
            senha: Senha do certificado

        Returns:
            Instância de CertificadoDigital com os dados extraídos

        Raises:
            FileNotFoundError: Se o arquivo não for encontrado
            ValueError: Se a senha estiver incorreta ou o arquivo for inválido
        """
        pfx_path = Path(pfx_path)
        if not pfx_path.exists():
            raise FileNotFoundError(f"Arquivo de certificado não encontrado: {pfx_path}")

        pfx_data = pfx_path.read_bytes()

        try:
            private_key, certificate, _additional_certs = pkcs12.load_key_and_certificates(
                pfx_data, senha.encode("utf-8")
            )
        except Exception as e:
            raise ValueError(f"Erro ao carregar certificado: {e}") from e

        if private_key is None:
            raise ValueError("Chave privada não encontrada no certificado")
        if certificate is None:
            raise ValueError("Certificado não encontrado no arquivo .pfx/.p12")

        cert_pem = certificate.public_bytes(Encoding.PEM)
        key_pem = private_key.private_bytes(
            Encoding.PEM,
            format=cryptography_private_format(),
            encryption_algorithm=NoEncryption(),
        )

        return cls(
            cert_pem=cert_pem,
            key_pem=key_pem,
            subject=certificate.subject.rfc4514_string(),
            issuer=certificate.issuer.rfc4514_string(),
            serial_number=certificate.serial_number,
            not_valid_after=certificate.not_valid_after_utc.isoformat(),
            not_valid_before=certificate.not_valid_before_utc.isoformat(),
        )

    def to_temp_files(self) -> tuple[str, str]:
        """Salva o certificado e a chave em arquivos temporários.

        Returns:
            Tupla com (caminho_cert, caminho_key) dos arquivos temporários
        """
        cert_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        cert_file.write(self.cert_pem)
        cert_file.close()

        key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        key_file.write(self.key_pem)
        key_file.close()

        return cert_file.name, key_file.name

    def cleanup_temp_files(self, cert_path: str, key_path: str) -> None:
        """Remove arquivos temporários de certificado."""
        for path in (cert_path, key_path):
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def cryptography_private_format():
    """Retorna o formato de serialização para chave privada."""
    from cryptography.hazmat.primitives.serialization import PrivateFormat
    return PrivateFormat.TraditionalOpenSSL
