# services/relatorio_service.py
import datetime
import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.colors import blue, red, black
import jwt
from jwt import InvalidTokenError

SECRET = "minhaChaveSuperSecretaParaJwtComTamanhoAdequado!"  # Deve ser a mesma do app.py

def get_colaborador_info_from_token(token: str) -> dict:
    """
    Extrai informações do colaborador do token JWT.
    Retorna dict com login, nome, etc.
    """
    try:
        # Remove "Bearer " se presente
        clean_token = token.replace("Bearer ", "") if token.startswith("Bearer ") else token
        payload = jwt.decode(clean_token, SECRET, algorithms=["HS256"])
        return {
            "login": payload.get("sub"),
            "nome": payload.get("name", payload.get("sub", "Colaborador")),
            "is_valid": True
        }
    except InvalidTokenError:
        return {"is_valid": False}

def gerar_pdf_relatorio(titulo: str, conteudo: str, colaborador_nome: str, data_hora: str) -> str:
    """
    Gera um arquivo PDF do relatório e retorna o caminho do arquivo.
    """
    # Cria diretório de relatórios se não existir
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
    
    # Nome do arquivo com timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"relatorio_{timestamp}_{colaborador_nome.replace(' ', '_')}.pdf"
    filepath = os.path.join(reports_dir, filename)
    
    # Criar o documento PDF
    doc = SimpleDocTemplate(filepath, pagesize=A4)
    styles = getSampleStyleSheet()
    
    # Estilos customizados
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=blue
    )
    
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        textColor=black
    )
    
    content_style = ParagraphStyle(
        'CustomContent',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=12,
        alignment=TA_JUSTIFY,
        leftIndent=20,
        rightIndent=20
    )
    
    # Construir o conteúdo do PDF
    story = []
    
    # Título do relatório
    story.append(Paragraph("CCR - RELATÓRIO DE INCIDENTE", title_style))
    story.append(Spacer(1, 20))
    
    # Informações do cabeçalho
    story.append(Paragraph(f"<b>Título:</b> {titulo}", header_style))
    story.append(Paragraph(f"<b>Data e Hora:</b> {data_hora}", header_style))
    story.append(Paragraph(f"<b>Colaborador Responsável:</b> {colaborador_nome}", header_style))
    story.append(Spacer(1, 20))
    
    # Conteúdo do relatório
    story.append(Paragraph("<b>Descrição do Incidente:</b>", header_style))
    story.append(Paragraph(conteudo, content_style))
    story.append(Spacer(1, 30))
    
    # Rodapé
    footer_text = f"Relatório gerado automaticamente pela Assistente Ceci em {data_hora}"
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=red
    )
    story.append(Paragraph(footer_text, footer_style))
    
    # Construir o PDF
    doc.build(story)
    
    return filepath

def gerar_relatorio(descricao: str, tipo_usuario: str = "Passageiro", token: str | None = None) -> dict:
    """
    Gera relatório apenas para colaboradores autenticados.
    Para passageiros, retorna erro de permissão.
    """
    # Verifica se é passageiro tentando gerar relatório
    if tipo_usuario != "Colaborador":
        return {
            "erro": "acesso_negado",
            "mensagem": "Desculpe, apenas colaboradores CCR podem gerar relatórios. Esta funcionalidade é restrita."
        }
    
    # Verifica se tem token válido
    if not token:
        return {
            "erro": "token_necessario", 
            "mensagem": "Token de autenticação necessário para gerar relatórios."
        }
    
    # Extrai informações do colaborador
    colaborador_info = get_colaborador_info_from_token(token)
    if not colaborador_info.get("is_valid"):
        return {
            "erro": "token_invalido",
            "mensagem": "Token inválido. Faça login novamente."
        }
    
    # Gera o relatório
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    colaborador_nome = colaborador_info.get("nome", "Colaborador CCR")
    titulo = f"Relatório de Incidente - {now.split(' ')[0]}"
    
    try:
        # Gera o PDF
        pdf_path = gerar_pdf_relatorio(titulo, descricao, colaborador_nome, now)
        pdf_filename = os.path.basename(pdf_path)
        
        return {
            "tipo": "relatorio",
            "titulo": titulo,
            "data_hora": now,
            "conteudo": descricao,
            "colaborador": colaborador_nome,
            "pdf_gerado": True,
            "pdf_path": pdf_path,
            "pdf_filename": pdf_filename,
            "download_url": f"/reports/download/{pdf_filename}",
            "list_url": "/reports/list",
            "mensagem": f"Relatório gerado com sucesso! PDF disponível para download.",
            "action_type": "pdf_generated"  # Para o frontend identificar
        }
    except Exception as e:
        return {
            "erro": "erro_geracao",
            "mensagem": f"Erro ao gerar PDF do relatório: {str(e)}",
            "tipo": "relatorio", 
            "titulo": titulo,
            "data_hora": now,
            "conteudo": descricao,
            "colaborador": colaborador_nome,
            "pdf_gerado": False
        }