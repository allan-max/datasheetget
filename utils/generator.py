# utils/generator.py
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from fpdf import FPDF
import os

# --- CONFIGURAÇÃO DO CABEÇALHO ---
LOGO_PATH = r"C:\Users\Administrator\Desktop\datasheetget\utils\ventura.png"

HEADER_INFO = {
    "empresa": "VENTURA COMERCIO DE INFORMÁTICA EIRELI",
    "cnpj": "CNPJ: 08.310.365/0001-24",
    "endereco": "RUA SETE 560 COCAL VILA VELHA – ES I 29105-770"
}

class DocGenerator:
    """Gera arquivos DOCX e PDF (Sem Preço, Logo Menor, Sem Linha)"""
    
    def _adicionar_cabecalho_word(self, doc):
        """Cria o cabeçalho no Word"""
        # Tabela invisível para alinhar texto à esquerda e logo à direita
        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        table.columns[0].width = Inches(4.5) 
        table.columns[1].width = Inches(2.0)

        # Lado Esquerdo (Texto da Empresa)
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
            try:
                run_img = p_img.add_run()
                # Diminuí de 1.4 para 0.9 polegadas
                run_img.add_picture(LOGO_PATH, width=Inches(0.9))
            except: pass
        
        # REMOVIDO: A linha divisória ("_" * 60)
        doc.add_paragraph("") # Apenas um espaço em branco para separar do título

    def create_word(self, data, filepath):
        try:
            doc = Document()
            
            # 1. Cabeçalho
            self._adicionar_cabecalho_word(doc)
            
            # 2. Título
            h = doc.add_heading(data.get("titulo", "Produto"), 0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # 3. Imagem Centralizada
            img_path = data.get("caminho_imagem_temp")
            if img_path and os.path.exists(img_path):
                try:
                    # Imagem do produto com tamanho equilibrado
                    doc.add_picture(img_path, width=Inches(3.2))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                except: pass

            # 4. Descrição
            doc.add_heading('Descrição', level=1)
            doc.add_paragraph(data.get("descricao", "Sem descrição disponível."))

            # 5. Ficha Técnica (AGORA PROTEGIDA PELO IF)
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

            # --- CABEÇALHO ---
            # Logo menor (w=30) e mais ajustada à direita
            if os.path.exists(LOGO_PATH):
                try: pdf.image(LOGO_PATH, x=165, y=8, w=30)
                except: pass
            
            pdf.set_xy(10, 10)
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(0, 5, txt(HEADER_INFO["empresa"]), ln=True)
            
            pdf.set_font("Helvetica", '', 8)
            pdf.cell(0, 4, txt(HEADER_INFO["cnpj"]), ln=True)
            pdf.cell(0, 4, txt(HEADER_INFO["endereco"]), ln=True)
            
            # REMOVIDO: A linha divisória (pdf.cell(0, 0, border='T'))
            pdf.ln(8) # Espaço extra antes do título
            # -----------------

            # Título
            pdf.set_font("Helvetica", 'B', 14)
            pdf.multi_cell(0, 8, txt(data.get("titulo", "Produto")), align='C')
            pdf.ln(5)

            # Imagem
            img_path = data.get("caminho_imagem_temp")
            if img_path and os.path.exists(img_path):
                try:
                    # Centraliza a imagem (largura A4 = 210mm)
                    # Imagem w=90 -> x = (210 - 90) / 2 = 60
                    x_pos = 60
                    pdf.image(img_path, x=x_pos, w=90)
                    pdf.ln(10)
                except: pass

            # Descrição
            pdf.set_font("Helvetica", 'B', 11)
            pdf.cell(0, 8, txt("Descrição"), ln=True)
            
            pdf.set_font("Helvetica", '', 10)
            pdf.multi_cell(0, 5, txt(data.get("descricao", "")[:3000]))
            pdf.ln(5)

            # Ficha Técnica (AGORA PROTEGIDA PELO IF)
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