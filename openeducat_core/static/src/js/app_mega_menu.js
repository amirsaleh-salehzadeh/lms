/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.isMegaMenuOpen = false;
    },

    toggleMegaMenu() {
        this.state.isMegaMenuOpen = !this.state.isMegaMenuOpen;
    },

    closeMegaMenu() {
        this.state.isMegaMenuOpen = false;
    },

    getMegaMenuColumns() {
        const apps = this.menuService.getApps().map((app) => ({
            app,
            sections: this.menuService.getMenuAsTree(app.id).childrenTree,
        }));
        const columnCount = Math.max(
            1,
            Math.min(apps.length, Math.floor((window.innerWidth - 50) / 266))
        );
        const columns = Array.from({ length: columnCount }, () => []);
        const columnWeights = Array(columnCount).fill(0);
        const countItems = (item) =>
            1 + (item.childrenTree || []).reduce((total, child) => total + countItems(child), 0);

        for (const entry of apps) {
            const weight = entry.sections.reduce((total, item) => total + countItems(item), 0) + 1;
            const columnIndex = columnWeights.indexOf(Math.min(...columnWeights));
            columns[columnIndex].push(entry);
            columnWeights[columnIndex] += weight;
        }

        return columns;
    },

    async openMegaMenuItem(menu) {
        this.closeMegaMenu();
        await this.menuService.selectMenu(menu);
    },
});
