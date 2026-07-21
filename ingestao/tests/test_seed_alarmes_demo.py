from ingestao import odoo_cliente, provisionar_demo, seed_alarmes_demo

DSN_ODOO = {'url': 'http://localhost:8189', 'db': 'sentinela', 'usuario': 'admin', 'senha': 'admin'}


def test_semear_cria_cenarios_com_status_variados_e_e_idempotente():
    # Nao faz cleanup de proposito: esta e a semente de demonstracao real do
    # painel de alarmes — o objetivo da task e deixar esses eventos no Odoo
    # da demo, nao so validar a funcao. `semear` e idempotente (verificado
    # abaixo), entao rodar este teste de novo nao duplica nada.
    cliente = odoo_cliente.conectar(**DSN_ODOO)
    provisionar_demo.provisionar(cliente)
    ids_primeira = seed_alarmes_demo.semear(cliente)
    assert len(ids_primeira) == len(seed_alarmes_demo.CENARIOS)

    eventos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'read', ids_primeira,
        fields=['status', 'timestamp_resolucao_sensor', 'tipo_violacao'],
    )
    assert any(e['timestamp_resolucao_sensor'] for e in eventos), 'esperado ao menos 1 cenario resolvido'
    assert any(not e['timestamp_resolucao_sensor'] for e in eventos), 'esperado ao menos 1 cenario ainda aberto'

    ids_segunda = seed_alarmes_demo.semear(cliente)
    assert ids_segunda == ids_primeira, 'rodar de novo nao deve duplicar eventos'
