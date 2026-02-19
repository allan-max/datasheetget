# config.py
import re

# ==============================================================================
# 📋 LISTA DE SITES SUPORTADOS
# ==============================================================================
  
  
SITES_CONFIG = {
    'MERCADO_LIVRE': {
        'padroes_url': [r'mercadolivre\.com', r'produto\.mercadolivre'],
        'modulo': 'mercado_livre',
        'classe': 'MercadoLivreScraper'
    },
    'AMAZON': {
        'padroes_url': [r'amazon\.com', r'amzn\.to'],
        'modulo': 'amazon',
        'classe': 'AmazonScraper'
    },
    'FUJIOKA': {
        'padroes_url': [r'fujioka\.com', r'fujiokadistribuidor\.com'],
        'modulo': 'fujioka',
        'classe': 'FujiokaScraper'
    },
    'FRIOPECAS': {
        'padroes_url': [r'friopecas\.com\.br'],
        'modulo': 'friopecas',
        'classe': 'FrioPecasBot'
    },
    'AGIS': {
        'padroes_url': [r'vendas\.agis\.com\.br', r'agis\.com\.br'],
        'modulo': 'agis',
        'classe': 'AgisScraper'
    },
    'MAGALU': {
        # Magalu Varejo (Comum)
        'padroes_url': [r'magazineluiza\.com\.br', r'magalu\.com'],
        'modulo': 'magalu',
        'classe': 'MagaluScraper'
    },
    'MAGALU_EMPRESAS': {
        # Magalu Empresas (B2B)
        'padroes_url': [r'magaluempresas\.com\.br'],
        'modulo': 'magalu_empresas',
        'classe': 'MagaluEmpresasScraper'
    },
    'PAUTA': {
        'padroes_url': [r'pauta\.com\.br'],
        'modulo': 'pauta',
        'classe': 'PautaScraper'
    },
     'INGRAM_MICRO': {
        # O regex abaixo pega tanto .com quanto .com.br para garantir
        'padroes_url': [r'ingrammicro\.com'], 
        'modulo': 'ingram_micro', 
        'classe': 'IngramMicroScraper'
    },
    'TAMBASA': {
        'padroes_url': [r'tambasa\.com', r'loja\.tambasa'],
        'modulo': 'tambasa',
        'classe': 'TambasaScraper'
    },
    'FRIGELAR': {
        'padroes_url': [r'frigelar\.com\.br'],
        'modulo': 'frigelar',
        'classe': 'FrigelarScraper'
    },
    'FASTSHOP': {
        'padroes_url': [r'fastshop\.com\.br', r'site\.fastshop'],
        'modulo': 'fastshop',
        'classe': 'FastShopScraper'
    },
    'ODERCO': {
        'padroes_url': [r'oderco\.com\.br'],
        'modulo': 'oderco',
        'classe': 'OdercoScraper'
    },
    'MAZER': {
        'padroes_url': [r'mazer\.com\.br'],
        'modulo': 'mazer',
        'classe': 'MazerScraper'
    },
    'DUTRA': {
        'padroes_url': [r'dutramaquinas\.com\.br'],
        'modulo': 'dutramaquinas',
        'classe': 'DutraMaquinasScraper'
    },
    'ROUTE66': {
        'padroes_url': [r'route66\.com\.br'],
        'modulo': 'router66',
        'classe': 'Router66Scraper'
    },
    'LOJADOMECANICO': {
        'padroes_url': [r'lojadomecanico\.com\.br'],
        'modulo': 'lojadomecanico',
        'classe': 'LojaDoMecanicoScraper'
    },
    'VONDER': {
        'padroes_url': [r'vonder\.com\.br'],
        'modulo': 'vonder',
        'classe': 'VonderScraper'
    },
    'MARTINS': {
        'padroes_url': [r'martinsatacado\.com\.br'],
        'modulo': 'martins',
        'classe': 'MartinsScraper'
    },
    'KALUNGA': {
        'padroes_url': [r'kalunga\.com\.br'],
        'modulo': 'kalunga',
        'classe': 'KalungaScraper'
    },
    'QUASETUDO': {
        'padroes_url': [r'quasetudodeinformatica\.com\.br'],
        'modulo': 'quasetudo',
        'classe': 'QuaseTudoScraper'
    },
    'BHPHOTOVIDEO': {
        'padroes_url': [r'bhphotovideo\.com'],
        'modulo': 'bhphotovideo',
        'classe': 'BhPhotoVideoScraper'
    },
    'intelbras': {
        # O padrão abaixo pega "intelbras.com", "intelbras.com.br", "loja.intelbras..."
        'padroes_url': [r'intelbras\.com'],
        'modulo': 'intelbras',
        'classe': 'IntelbrasScraper'
    },
    'KABUM': {
        'padroes_url': [r'kabum\.com\.br'],
        'modulo': 'kabum',
        'classe': 'KabumScraper'
    },
    'DELL': {
        'padroes_url': [r'dell\.com'],
        'modulo': 'dell',
        'classe': 'DellScraper'
    },
    'DIMENSIONAL': {
        'padroes_url': [r'dimensional\.com\.br'],
        'modulo': 'dimensional',
        'classe': 'DimensionalScraper'
    },
    'HAYAMAX': {
        'padroes_url': [r'hayamax\.com\.br'],
        'modulo': 'hayamax',
        'classe': 'HayamaxScraper'
    },
    'WEG': {
        'padroes_url': [r'weg\.net'],
        'modulo': 'weg',
        'classe': 'WegScraper'
    }
}

def identificar_site(url):
    """
    Verifica se a URL pertence a algum site configurado.
    Retorna: (Nome do Site, Nome do Modulo, Nome da Classe)
    """
    for site_nome, config in SITES_CONFIG.items():
        for padrao in config['padroes_url']:
            # Verifica se o padrão existe na URL (Ignora maiúsculas/minúsculas)
            if re.search(padrao, url, re.IGNORECASE):
                return site_nome, config['modulo'], config['classe']
    
    return None, None, None