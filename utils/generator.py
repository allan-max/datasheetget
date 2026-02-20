# utils/generator.py
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
from PIL import Image  # Necessário para redimensionar
import os

# --- CONFIGURAÇÃO ---
LOGO_PATH = r"C:\Users\Administrator\Desktop\datasheetget\utils\ventura.png"

HEADER_INFO = {
    "empresa": "VENTURA COMERCIO DE INFORMÁTICA EIRELI",
    "cnpj": "CNPJ: 08.310.365/0001-24",
    "endereco": "RUA SETE 560 COCAL VILA VELHA – ES I 29105-770"
}

# LIMITES MÁXIMOS PARA A IMAGEM DO PRODUTO (EM PIXELS)
# Isso impede que imagens muito altas estourem o layout
MAX_IMG_WIDTH = 800
MAX_IMG_HEIGHT = 500  # <-- Altura máxima permitida

class DocGenerator:
    """Gera arquivos DOCX e PDF com controle de tamanho de imagem"""
    
    def _redimensionar_imagem(self, image_path):
        """
        Abre a imagem temporária, verifica se ela excede os limites
        de largura ou altura e a redimensiona proporcionalmente se necessário.
        Sobrescreve o arquivo original.
        """
        try:
            img = Image.open(image_path)
            width, height = img.size
            
            # Calcula a proporção atual
            aspect_ratio = width / height
            
            new_width = width
            new_height = height

            # 1. Verifica se a largura estoura o limite
            if new_width > MAX_IMG_WIDTH:
                new_width = MAX_IMG_WIDTH
                new_height = int(new_width / aspect_ratio)
            
            # 2. Verifica se a altura (mesmo após ajustar largura) ainda estoura o limite
            # Este é o passo crucial para o seu pedido
            if new_height > MAX_IMG_HEIGHT:
                new_height = MAX_IMG_HEIGHT
                new_width = int(new_height * aspect_ratio)

            # Se houve necessidade de redimensionar
            if (new_width, new_height) != (width, height):
                # Usa LANCZOS para melhor qualidade na redução
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                # Salva por cima do arquivo original
                img.save(image_path, quality=95, optimize=True)
                # print(f"   [GERADOR] Imagem redimensionada de {width}x{height} para {new_width}x{new_height}")
            
            return True
        except Exception as e:
            print(f"   ⚠️ Erro ao tentar redimensionar imagem: {e}")
            # Se der erro, segue com a imagem original mesmo
            return False

    def _adicionar_cabecalho_word(self, doc):
        """Cria o cabeçalho no Word"""
        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        table.columns[0].width = Inches(4.5) 
        table.columns[1].width = Inches(2.0)

        # Lado Esquerdo
        cell_text = table.cell(0, 0)
        p = cell_text.paragraphs[0]
        run_nome = p.add_run(HEADER_INFO["empresa"] + "\n")
        run_nome.bold = True
        run_nome.font.size = Pt(11)
        run_nome.font.name = 'Arial'
        run_rest = p.add_run(f"{HEADER_INFO['cnpj']}\n{HEADER_INFO['endereco']}")
        run_rest.font.size = Pt(9)
        run_rest.font.name = 'Arial'

        # Lado Direito (Logo)
        cell_img = table.cell(0, 1)
        p_img = cell_img.paragraphs[0]
        p_img.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if os.path.exists(LOGO_PATH):
            try: run_img = p_img.add_run().add_picture(LOGO_PATH, width=Inches(0.9))
            except: pass
        doc.add_paragraph("")

    def create_word(self, data, filepath):
        try:
            doc = Document()
            self._adicionar_cabecalho_word(doc)
            
            # Título
            h = doc.add_heading(data.get("titulo", "Produto"), 0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # --- IMAGEM (COM REDIMENSIONAMENTO) ---
            img_path = data.get("caminho_imagem_temp")
            if img_path and os.path.exists(img_path):
                # 1. Chama a função para garantir o tamanho máximo
                self._redimensionar_imagem(img_path)
                try:
                    # 2. Insere no Word. Definimos apenas a largura (Inches(3.2)),
                    # a altura será automática, mas agora sabemos que não excederá o limite.
                    doc.add_picture(img_path, width=Inches(3.2))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                except: pass
            # --------------------------------------

            # Descrição
            doc.add_heading('Descrição', level=1)
            doc.add_paragraph(data.get("descricao", "Sem descrição disponível."))

            # Ficha Técnica (Condicional)
            specs = data.get("caracteristicas", {})
            if specs:
                doc.add_heading('Ficha Técnica', level=1)
                table = doc.add_table(rows=0, cols=2)
                table.style = 'Table Grid'
                hdr = table.add_row().cells
                hdr[0].text = 'Item'
                hdr[1].text = 'Detalhe'
                items = specs.items() if isinstance(specs, dict) else specs
                for k, v in items:
                    row = table.add_row().cells
                    row[0].text = str(k)
                    row[1].text = str(v)

            doc.save(filepath)
            return True
        except Exception as e:
            print(f"   [ERRO WORD] {e}")
            return False

    def create_pdf(self, data, filepath):
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)
            def txt(s):
                s = str(s).replace('’', "'").replace('“', '"').replace('”', '"')
                return s.encode('latin-1', 'replace').decode('latin-1')

            # Cabeçalho PDF
            if os.path.exists(LOGO_PATH):
                try: pdf.image(LOGO_PATH, x=165, y=8, w=30)
                except: pass
            pdf.set_xy(10, 10)
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(0, 5, txt(HEADER_INFO["empresa"]), ln=True)
            pdf.set_font("Helvetica", '', 8)
            pdf.cell(0, 4, txt(HEADER_INFO["cnpj"]), ln=True)
            pdf.cell(0, 4, txt(HEADER_INFO["endereco"]), ln=True)
            pdf.ln(8)

            # Título
            pdf.set_font("Helvetica", 'B', 14)
            pdf.multi_cell(0, 8, txt(data.get("titulo", "Produto")), align='C')
            pdf.ln(5)

            # --- IMAGEM PDF (COM REDIMENSIONAMENTO) ---
            img_path = data.get("caminho_imagem_temp")
            if img_path and os.path.exists(img_path):
                # 1. Chama a função para garantir o tamanho máximo
                self._redimensionar_imagem(img_path)
                try:
                    # Centralização no PDF (A4 largura ~210mm)
                    # Definimos largura w=90mm. A altura será proporcional e controlada.
                    x_pos = (210 - 90) / 2 
                    pdf.image(img_path, x=x_pos, w=90)
                    pdf.ln(10)
                except: pass
            # ------------------------------------------

            # Descrição
            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(0, 8, txt("Descrição"), ln=True)
            pdf.set_font("Helvetica", '', 10)
            pdf.multi_cell(0, 5, txt(data.get("descricao", "")[:3000]))
            pdf.ln(5)

            # Ficha Técnica (Condicional)
            specs = data.get("caracteristicas", {})
            if specs:
                pdf.set_font("Helvetica", 'B', 11)
                pdf.cell(0, 8, txt("Ficha Técnica"), ln=True)
                items = specs.items() if isinstance(specs, dict) else specs
                for k, v in items:
                    pdf.set_font("Helvetica", 'B', 9)
                    pdf.set_fill_color(240, 240, 240)
                    pdf.cell(0, 6, txt(str(k)), ln=True, fill=True)
                    pdf.set_font("Helvetica", '', 9)
                    pdf.multi_cell(0, 5, txt(str(v)), border='B')
                    pdf.ln(1)

            pdf.output(filepath)
            return True
        except Exception as e:
            print(f"   [ERRO PDF] {e}")
            return False