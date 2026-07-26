/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.PortalAutenticidadePolling = publicWidget.Widget.extend({
    selector: "#job",

    /**
     * @override
     */
    start() {
        this.jobId = this.el.dataset.jobId;
        if (this.jobId) {
            this.pollTimer = setInterval(() => this._poll(), 2000);
        }
        return this._super(...arguments);
    },

    /**
     * @override
     */
    destroy() {
        this._parar();
        this._super(...arguments);
    },

    _parar() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    },

    async _poll() {
        let resp;
        try {
            resp = await fetch(`/verificar-autenticidade/${this.jobId}`, {
                headers: { Accept: "application/json" },
            });
        } catch (e) {
            // rede instável: tenta de novo no próximo tick
            return;
        }
        // Quando o job fica 'pronto' o controller renderiza o relatório
        // (HTML) mesmo com Accept: application/json — nesse caso o
        // Content-Type da resposta deixa de ser JSON e basta recarregar
        // a página para exibi-lo.
        const contentType = resp.headers.get("Content-Type") || "";
        if (!contentType.includes("application/json")) {
            this._parar();
            window.location.reload();
            return;
        }
        let data;
        try {
            data = await resp.json();
        } catch (e) {
            return;
        }
        if (data.estado === "fila" || data.estado === "processando") {
            const posEl = this.el.querySelector(".js_posicao span");
            if (posEl && typeof data.posicao !== "undefined") {
                posEl.textContent = data.posicao;
            }
        } else {
            // erro / expirado: recarrega
            this._parar();
            window.location.reload();
        }
    },
});

export default publicWidget.registry.PortalAutenticidadePolling;
