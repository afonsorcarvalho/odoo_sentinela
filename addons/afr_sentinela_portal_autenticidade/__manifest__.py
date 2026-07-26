# NOTA DE DEPLOY: este portal é público e faz rate-limit por IP no api a
# partir do IP que o Odoo enxerga (controllers/portal.py:_ip). Em produção,
# Odoo DEVE rodar com --proxy-mode / proxy_mode=True atrás de um proxy
# confiável (nginx/traefik) para que esse IP reflita o cliente real.
{
    'name': 'Sentinela — Portal de Autenticidade',
    'version': '18.0.1.0.0',
    'category': 'Website',
    'summary': 'Portal público para verificar a autenticidade de arquivos de leitura assinados',
    'depends': ['website', 'afr_sentinela_sensor_monitor'],
    'data': [
        'views/portal_templates.xml',
        # 'report/laudo_report.xml',        # criado no Stage 5 (deixar comentado até lá)
        # 'report/laudo_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'afr_sentinela_portal_autenticidade/static/src/js/portal_polling.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
