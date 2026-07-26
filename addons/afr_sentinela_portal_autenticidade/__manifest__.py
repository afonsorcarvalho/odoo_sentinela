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
