# Product

## Register

product

## Users

Duas audiências, mesma superfície (SPA React em `frontend/`):

- **Técnicos e enfermeiros de CME** (Central de Material e Esterilização) hospitalar: consultam o dashboard durante o turno, muitas vezes sob pressão operacional, luvas, ambiente clínico iluminado. Job: verificar rapidamente se sensores (temperatura/pressão/etc.) estão dentro de faixa regulatória e agir sobre alarmes.
- **Operador interno do SaaS**: visão consolidada multi-cliente/multi-site, mesma stack de identidade (Odoo como provedor).

Contexto de uso: monitoramento contínuo, não uma tarefa pontual — a tela fica "de fundo" a maior parte do tempo, mas precisa comunicar estado crítico instantaneamente quando algo sai de faixa.

## Product Purpose

Dashboard de monitoramento em tempo real para conformidade regulatória (RDC 15/ANVISA) de sensores em CME hospitalar: leitura ao vivo, séries temporais históricas com limites regulatórios sobrepostos, e ciclo de vida de alarmes. Sucesso = o time de CME nunca é pego de surpresa por uma violação de faixa, e consegue provar conformidade em auditoria.

Não inclui as telas administrativas/cadastro (essas ficam no Odoo nativo/OWL — ver `frontend_spec.md` seção 1). A SPA é só a vitrine de monitoramento voltada ao cliente.

## Brand Personality

Clínico, preciso, sério. Tom regulatório-técnico — não é um produto de consumo, é instrumentação de compliance em ambiente de saúde. Confiança vem de precisão e ausência de ambiguidade visual, não de calor ou personalidade lúdica.

## Anti-references

Evitar o clichê de dashboard SaaS genérico: hero-metric template, cards idênticos repetidos, gradient text, glassmorphism decorativo. O produto não está vendendo uma métrica de vaidade — está reportando estado operacional/regulatório real.

## Design Principles

1. **Estado de alarme nunca é ambíguo.** Já houve bug real de `color-mix` em OKLCH invertendo a leitura crítico↔ok pela interpolação de matiz (ver [[echarts-appendData-line]] e memória do projeto) — cor de status é a linha vermelha do produto, não decoração.
2. **Clareza sobre densidade.** A tela fica de fundo a maior parte do tempo; quando importa, precisa ser lida em um relance, não decodificada.
3. **Contraste alto por padrão.** WCAG AA (light/dark, já verificado) é piso, não teto — CME tem iluminação forte, então contraste generoso é preferível a contraste "elegante e discreto".
4. **Sem enfeite que compita com o dado.** Nada de gradientes, glass ou animação decorativa disputando atenção com um valor fora de faixa.
5. **Identidade única via Odoo.** Toda decisão de UI que toque permissão/escopo de dados respeita a mesma fonte de verdade do Odoo (`ir.rule`/`partner_id`) — a SPA nunca decide sozinha quem vê o quê.

## Accessibility & Inclusion

- **WCAG AA**, light e dark, já implementado e testado (ver testes em `frontend/src/components/*.test.tsx` e memória "SensorDetail ✓ ... WCAG AA light/dark/mobile").
- **Alto contraste para ambiente iluminado**: CME hospitalar tem iluminação forte — considerar reforçar contraste além do mínimo AA nos estados críticos, não só atingir o piso.
- Cores de status usam OKLCH com matiz "none" para evitar deriva de matiz em `color-mix` (crit→roxo, warn→verde) — ver `frontend/src/index.css` e `statusVisuals.tsx`.
