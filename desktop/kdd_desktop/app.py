"""Janela principal do cliente de consulta KDD (somente leitura)."""
from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .api_client import KddApiError, KddClient
from .config import Config


class MainWindow(QMainWindow):
    def __init__(self, client: KddClient) -> None:
        super().__init__()
        self._client = client
        self.setWindowTitle("KDD — Consulta de Mapas Conceituais")
        self.resize(1180, 720)
        self._montar_ui()
        self._recarregar()

    # ── construção da UI ──
    def _montar_ui(self) -> None:
        # Esquerda: busca + árvore de áreas
        self.busca = QLineEdit(placeholderText="Buscar conceito por rótulo e Enter…")
        self.busca.returnPressed.connect(self._buscar)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabel("Áreas")
        self.arvore.itemClicked.connect(self._area_selecionada)

        btn_todas = QPushButton("Todos os conceitos")
        btn_todas.clicked.connect(lambda: self._listar_conceitos())
        btn_const = QPushButton("Constelação…")
        btn_const.clicked.connect(self._abrir_constelacao)

        esquerda = QWidget()
        le = QVBoxLayout(esquerda)
        le.addWidget(self.busca)
        le.addWidget(self.arvore, 1)
        le.addWidget(btn_todas)
        le.addWidget(btn_const)

        # Centro: tabela de conceitos
        self.tabela = QTableWidget(0, 3)
        self.tabela.setHorizontalHeaderLabels(["ID", "Rótulos", "Áreas"])
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.cellClicked.connect(self._conceito_selecionado)

        # Direita: detalhe
        self.detalhe = QTextBrowser()
        self.detalhe.setOpenExternalLinks(False)

        split = QSplitter()
        split.addWidget(esquerda)
        split.addWidget(self.tabela)
        split.addWidget(self.detalhe)
        split.setSizes([260, 420, 480])
        self.setCentralWidget(split)

        barra = self.addToolBar("Principal")
        atualizar = QPushButton("Atualizar")
        atualizar.clicked.connect(self._recarregar)
        barra.addWidget(atualizar)

        self.statusBar().showMessage("Pronto.")

    # ── ações ──
    def _recarregar(self) -> None:
        try:
            self._client.saude()
            self._carregar_areas()
            self._listar_conceitos()
            self.statusBar().showMessage(f"Conectado a {self._client._cfg.base_url}")
        except KddApiError as e:
            self._erro(str(e))

    def _carregar_areas(self) -> None:
        self.arvore.clear()

        def adicionar(pai: QTreeWidgetItem | None, no: dict[str, Any]) -> None:
            item = QTreeWidgetItem([no["nome"]])
            item.setData(0, Qt.ItemDataRole.UserRole, no["id"])
            (pai.addChild if pai else self.arvore.addTopLevelItem)(item)
            for filho in no.get("filhos", []):
                adicionar(item, filho)

        for raiz in self._client.areas():
            adicionar(None, raiz)
        self.arvore.expandAll()

    def _area_selecionada(self, item: QTreeWidgetItem) -> None:
        area_id = item.data(0, Qt.ItemDataRole.UserRole)
        self._listar_conceitos(area=int(area_id))

    def _buscar(self) -> None:
        self._listar_conceitos(q=self.busca.text().strip() or None)

    def _listar_conceitos(self, q: str | None = None, area: int | None = None) -> None:
        try:
            conceitos = self._client.conceitos(q=q, area=area)
        except KddApiError as e:
            self._erro(str(e))
            return
        self.tabela.setRowCount(0)
        for c in conceitos:
            linha = self.tabela.rowCount()
            self.tabela.insertRow(linha)
            self.tabela.setItem(linha, 0, QTableWidgetItem(str(c["id"])))
            self.tabela.setItem(linha, 1, QTableWidgetItem(c.get("rotulos") or ""))
            self.tabela.setItem(linha, 2, QTableWidgetItem(c.get("areas") or ""))
        alvo = "todos" if not (q or area) else (f"q='{q}'" if q else f"área {area}")
        self.statusBar().showMessage(f"{len(conceitos)} conceito(s) — {alvo}")

    def _conceito_selecionado(self, linha: int, _coluna: int) -> None:
        item = self.tabela.item(linha, 0)
        if item:
            self._mostrar_detalhe(int(item.text()))

    def _mostrar_detalhe(self, conceito_id: int) -> None:
        try:
            c = self._client.conceito(conceito_id)
        except KddApiError as e:
            self._erro(str(e))
            return
        self.detalhe.setHtml(_html_conceito(c))

    def _abrir_constelacao(self) -> None:
        try:
            dados = self._client.constelacao()
        except KddApiError as e:
            self._erro(str(e))
            return
        ConstelacaoDialog(dados, self).exec()

    def _erro(self, msg: str) -> None:
        self.statusBar().showMessage(msg)
        QMessageBox.warning(self, "Erro", msg)


class ConstelacaoDialog(QDialog):
    def __init__(self, dados: dict[str, Any], pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Constelação — visão macro")
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Áreas, pontes interdisciplinares e homônimos</b>"))
        visor = QTextBrowser()
        visor.setHtml(_html_constelacao(dados))
        layout.addWidget(visor, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)


def _e(txt: Any) -> str:
    return html.escape(str(txt if txt is not None else ""))


def _html_conceito(c: dict[str, Any]) -> str:
    if not c:
        return "<i>Conceito não encontrado.</i>"
    linhas = [f"<h2>{_e(c.get('sentido'))}</h2>", f"<p><small>conceito #{_e(c.get('id'))}</small></p>"]

    rotulos = c.get("rotulos", [])
    if rotulos:
        itens = ", ".join(
            f"<b>{_e(r['texto'])}</b>" if r.get("principal") else _e(r["texto"]) for r in rotulos
        )
        linhas.append(f"<p><b>Rótulos:</b> {itens}</p>")

    areas = c.get("areas", [])
    if areas:
        linhas.append("<p><b>Áreas:</b> " + ", ".join(_e(a["nome"]) for a in areas) + "</p>")

    fontes = c.get("fontes", [])
    if fontes:
        linhas.append("<p><b>Fontes:</b></p><ul>")
        for f in fontes:
            linhas.append(f"<li>{_e(f.get('titulo'))} — <i>{_e(f.get('status_aprovacao'))}</i></li>")
        linhas.append("</ul>")

    def bloco(titulo: str, props: list[dict[str, Any]], chave: str) -> None:
        if not props:
            return
        linhas.append(f"<p><b>{titulo}:</b></p><ul>")
        for p in props:
            outro = p.get(chave, {})
            linhas.append(
                f"<li>{_e(p.get('relacao'))} → {_e(outro.get('rotulo'))} "
                f"<span style='color:#888'>(certeza: {_e(p.get('fontes_aprovadas'))} fonte(s))</span></li>"
            )
        linhas.append("</ul>")

    bloco("Proposições (origem)", c.get("proposicoes_origem", []), "destino")
    bloco("Proposições (destino)", c.get("proposicoes_destino", []), "origem")
    return "\n".join(linhas)


def _html_constelacao(d: dict[str, Any]) -> str:
    out = ["<h3>Áreas</h3><ul>"]
    for a in d.get("areas", []):
        out.append(f"<li>{_e(a['nome'])} — {_e(a['conceitos'])} conceito(s)</li>")
    out.append("</ul><h3>Pontes interdisciplinares</h3>")
    pontes = d.get("pontes", [])
    if pontes:
        out.append("<ul>")
        for p in pontes:
            out.append(
                f"<li>{_e(p['origem']['rotulo'])} —<i>{_e(p['relacao'])}</i>→ {_e(p['destino']['rotulo'])}</li>"
            )
        out.append("</ul>")
    else:
        out.append("<p><i>Nenhuma ponte ainda.</i></p>")
    out.append("<h3>Homônimos</h3>")
    homs = d.get("homonimos", [])
    if homs:
        out.append("<ul>")
        for h in homs:
            out.append(f"<li><b>{_e(h['rotulo'])}</b>: {_e(h['sentidos'])} sentidos (conceitos {_e(h['conceito_ids'])})</li>")
        out.append("</ul>")
    else:
        out.append("<p><i>Nenhum homônimo ainda.</i></p>")
    return "\n".join(out)


def main() -> int:
    app = QApplication([])
    try:
        client = KddClient(Config.carregar())
    except RuntimeError as e:
        QMessageBox.critical(None, "Configuração", str(e))
        return 1
    janela = MainWindow(client)
    janela.show()
    return app.exec()
