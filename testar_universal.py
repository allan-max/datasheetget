import os
import sys

from scrapers.universal import UniversalScraper


def main(urls):
    if not urls:
        print("Uso: python testar_universal.py <url> [<url> ...]")
        return 2
    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(pasta, exist_ok=True)
    for url in urls:
        scraper = UniversalScraper(url)
        scraper.output_folder = pasta
        resultado = scraper.executar()
        print("URL: " + url)
        if not resultado["sucesso"]:
            print("Falha: " + resultado["erro"])
            continue
        print("Fonte: " + resultado["fonte"])
        print("Titulo: " + resultado["titulo"])
        print("Specs: " + str(len(resultado["caracteristicas"])))
        print("Descricao: " + resultado["descricao"][:250].replace("\n", " "))
        print("Imagem: " + str(resultado["total_imagens"]))
        print("Word: " + resultado["arquivos"]["full_path_word"])
        print("PDF: " + resultado["arquivos"]["full_path_pdf"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
