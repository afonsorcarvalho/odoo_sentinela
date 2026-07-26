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
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this._super(...arguments);
    },

    async _poll() {
        let data;
        try {
            const resp = await fetch(`/verificar-autenticidade/${this.jobId}`);
            data = await resp.json();
        } catch (e) {
            // rede instável: tenta de novo no próximo tick
            return;
        }
        if (data.estado === "fila" || data.estado === "processando") {
            const posEl = this.el.querySelector(".js_posicao span");
            if (posEl && typeof data.posicao !== "undefined") {
                posEl.textContent = data.posicao;
            }
        } else {
            // pronto / erro / expirado: recarrega para o controller
            // renderizar o relatório (Stage 5)
            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
            window.location.reload();
        }
    },
});

export default publicWidget.registry.PortalAutenticidadePolling;
