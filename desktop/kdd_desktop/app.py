"""Janela principal do cliente de consulta KDD (somente leitura)."""
from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
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
        # currentCellChanged cobre mouse e teclado; evita a busca dupla do detalhe
        # que ocorria ao conectar também o cellClicked (dois GET /conceitos/{id}).
        self.tabela.currentCellChanged.connect(self._linha_mudou)

        # Direita: detalhe
        self.detalhe = QTextBrowser()
        self.detalhe.setOpenExternalLinks(False)

        split = QSplitter()
        split.addWidget(esquerda)
        split.addWidget(self.tabela)
        split.addWidget(self.detalhe)
        split.setSizes([260, 420, 480])

        # Centro em abas; a 1ª aba é a navegação de áreas e conceitos.
        self.tabs = QTabWidget()
        self.tabs.addTab(split, "Áreas e Conceitos")
        from .mapa import MapasTab
        self.tabs.addTab(MapasTab(self._client), "Mapas")
        self.tabs.addTab(FilaTab(self._client), "Fila")
        self.setCentralWidget(self.tabs)

        barra = self.addToolBar("Principal")
        atualizar = QPushButton("Atualizar")
        atualizar.clicked.connect(self._recarregar)
        barra.addWidget(atualizar)

        b_mapas = QPushButton("🗺 Mapas")
        b_mapas.clicked.connect(self._abrir_mapas)
        barra.addWidget(b_mapas)

        b_pdf = QPushButton("⬆ Enviar documento")
        b_pdf.clicked.connect(self._enviar_pdf)
        barra.addWidget(b_pdf)

        # Ações de edição — só quando há token de validador (perfil de curadoria)
        if self._client.pode_editar():
            barra.addSeparator()
            b_novo = QPushButton("＋ Conceito")
            b_novo.clicked.connect(self._novo_conceito)
            barra.addWidget(b_novo)
            b_editar = QPushButton("✎ Editar conceito")
            b_editar.clicked.connect(self._editar_conceito_atual)
            barra.addWidget(b_editar)
            b_area = QPushButton("＋ Área")
            b_area.clicked.connect(self._nova_area)
            barra.addWidget(b_area)
            self.statusBar().showMessage("Pronto. (modo edição disponível — validador)")
        else:
            self.statusBar().showMessage("Pronto. (somente leitura — sem token de validador)")

        self._conceito_atual: int | None = None

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

    def _linha_mudou(self, linha: int, _c: int = -1, _pl: int = -1, _pc: int = -1) -> None:
        if linha >= 0:
            item = self.tabela.item(linha, 0)
            if item:
                self._mostrar_detalhe(int(item.text()))

    def _mostrar_detalhe(self, conceito_id: int) -> None:
        try:
            c = self._client.conceito(conceito_id)
        except KddApiError as e:
            self._erro(str(e))
            return
        self._conceito_atual = conceito_id
        self.detalhe.setHtml(_html_conceito(c))

    # ── ações de edição ──
    def _novo_conceito(self) -> None:
        sentido, ok = QInputDialog.getText(self, "Novo conceito", "Sentido (identidade do conceito):")
        if not ok or not sentido.strip():
            return
        rotulo, ok = QInputDialog.getText(self, "Novo conceito", "Rótulo principal:")
        if not ok or not rotulo.strip():
            return
        areas_txt, ok = QInputDialog.getText(self, "Novo conceito", "Áreas (separadas por vírgula, opcional):")
        areas = [a.strip() for a in areas_txt.split(",") if a.strip()] if ok else []
        try:
            r = self._client.criar_conceito(sentido.strip(), rotulo.strip(), areas)
        except KddApiError as e:
            self._erro(str(e))
            return
        self._listar_conceitos()
        self._mostrar_detalhe(int(r["conceito"]["id"]))
        self.statusBar().showMessage(f"Conceito #{r['conceito']['id']} criado.")

    def _editar_conceito_atual(self) -> None:
        if not self._conceito_atual:
            QMessageBox.information(self, "Editar", "Selecione um conceito primeiro.")
            return
        dlg = ConceitoEditorDialog(self._client, self._conceito_atual, self)
        dlg.exec()
        self._listar_conceitos()
        self._mostrar_detalhe(self._conceito_atual)

    def _nova_area(self) -> None:
        nome, ok = QInputDialog.getText(self, "Nova área", "Nome da área:")
        if not ok or not nome.strip():
            return
        try:
            self._client.criar_area(nome.strip())
        except KddApiError as e:
            self._erro(str(e))
            return
        self._carregar_areas()
        self.statusBar().showMessage(f"Área '{nome.strip()}' criada.")

    def _abrir_mapas(self) -> None:
        from .mapa import MapasDialog
        MapasDialog(self._client, self).exec()
        self._listar_conceitos()

    def _enviar_pdf(self) -> None:
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolher documento", "", "Documentos (*.pdf *.txt);;PDF (*.pdf);;Texto (*.txt)")
        if not caminho:
            return
        sugestao = Path(caminho).stem
        titulo, ok = QInputDialog.getText(self, "Enviar documento", "Título do documento:", text=sugestao)
        if not ok:
            return
        try:
            r = self._client.enviar_documento(caminho, titulo.strip() or sugestao)
        except KddApiError as e:
            self._erro(str(e))
            return
        f = r.get("fonte", {})
        if r.get("duplicado"):
            QMessageBox.information(
                self, "PDF já enviado",
                f"Este PDF (mesmo conteúdo) já existe como fonte #{f.get('id')} "
                f"(proc: {f.get('status_proc')}). Não será reprocessado.")
        else:
            QMessageBox.information(
                self, "PDF enviado",
                f"Enviado como fonte #{f.get('id')} (pendente). O bot vai processá-lo "
                f"na próxima varredura (main.py --loop).")
        self.statusBar().showMessage(f"Upload concluído: fonte #{f.get('id')}")

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

    # Conceitos mais intimamente ligados (vizinhos diretos, por força do vínculo)
    ligados = _conceitos_ligados(c, limite=10)
    if ligados:
        linhas.append("<p><b>Conceitos mais ligados:</b></p><ol>")
        for v in ligados:
            linhas.append(
                f"<li>{_e(v['rotulo'])} "
                f"<span style='color:#888'>({v['ligacoes']} ligação(ões), certeza {v['certeza']})</span></li>"
            )
        linhas.append("</ol>")

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


def _conceitos_ligados(c: dict[str, Any], limite: int = 10) -> list[dict[str, Any]]:
    """Vizinhos diretos do conceito, agregados por força do vínculo.

    Conta quantas proposições ligam a cada vizinho e soma a certeza dessas
    proposições; ordena por (nº de ligações, certeza) e devolve os ``limite`` maiores.
    """
    agg: dict[int, dict[str, Any]] = {}
    for prop, chave in ((c.get("proposicoes_origem", []), "destino"),
                        (c.get("proposicoes_destino", []), "origem")):
        for p in prop:
            outro = p.get(chave, {})
            oid = outro.get("id")
            if oid is None:
                continue
            v = agg.setdefault(oid, {"rotulo": outro.get("rotulo") or f"#{oid}", "ligacoes": 0, "certeza": 0})
            v["ligacoes"] += 1
            v["certeza"] += int(p.get("fontes_aprovadas") or 0)
    ordenado = sorted(agg.values(), key=lambda v: (v["ligacoes"], v["certeza"]), reverse=True)
    return ordenado[:limite]


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


class EscolherConceitoDialog(QDialog):
    """Busca e seleciona um conceito (para destino de proposição, merge, etc.)."""

    def __init__(self, client: KddClient, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self._client = client
        self.escolhido: int | None = None
        self.setWindowTitle("Escolher conceito")
        self.resize(460, 420)
        layout = QVBoxLayout(self)
        self.busca = QLineEdit(placeholderText="Buscar por rótulo e Enter…")
        self.busca.returnPressed.connect(self._buscar)
        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(lambda _i: self._confirmar())
        layout.addWidget(self.busca)
        layout.addWidget(self.lista, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self._buscar()

    def _buscar(self) -> None:
        self.lista.clear()
        try:
            conceitos = self._client.conceitos(q=self.busca.text().strip() or None)
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        for c in conceitos:
            it = QListWidgetItem(f"#{c['id']} — {c.get('rotulos') or ''}  ({c.get('sentido') or ''})")
            it.setData(Qt.ItemDataRole.UserRole, int(c["id"]))
            self.lista.addItem(it)

    def _confirmar(self) -> None:
        it = self.lista.currentItem()
        if it:
            self.escolhido = int(it.data(Qt.ItemDataRole.UserRole))
            self.accept()


class ConceitoEditorDialog(QDialog):
    """Editor de um conceito: sentido, rótulos, áreas, proposições, merge e split."""

    def __init__(self, client: KddClient, conceito_id: int, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self._client = client
        self._cid = conceito_id
        self.setWindowTitle(f"Editar conceito #{conceito_id}")
        self.resize(640, 680)
        self._montar()
        self._carregar()

    def _montar(self) -> None:
        layout = QVBoxLayout(self)

        # Sentido
        gs = QGroupBox("Sentido (identidade)")
        ls = QHBoxLayout(gs)
        self.sentido = QLineEdit()
        b_sentido = QPushButton("Salvar")
        b_sentido.clicked.connect(self._salvar_sentido)
        ls.addWidget(self.sentido, 1)
        ls.addWidget(b_sentido)
        layout.addWidget(gs)

        # Rótulos
        gr = QGroupBox("Rótulos")
        lr = QVBoxLayout(gr)
        self.rotulos = QListWidget()
        lr.addWidget(self.rotulos)
        br = QHBoxLayout()
        for txt, fn in [("Adicionar", self._add_rotulo), ("Tornar principal", self._principal),
                        ("Remover", self._rem_rotulo)]:
            b = QPushButton(txt); b.clicked.connect(fn); br.addWidget(b)
        lr.addLayout(br)
        layout.addWidget(gr)

        # Áreas
        ga = QGroupBox("Áreas")
        la = QVBoxLayout(ga)
        self.areas = QListWidget()
        la.addWidget(self.areas)
        ba = QHBoxLayout()
        for txt, fn in [("Adicionar área", self._add_area), ("Remover área", self._rem_area)]:
            b = QPushButton(txt); b.clicked.connect(fn); ba.addWidget(b)
        la.addLayout(ba)
        layout.addWidget(ga)

        # Proposições (origem)
        gp = QGroupBox("Proposições (este conceito como origem)")
        lp = QVBoxLayout(gp)
        self.props = QTableWidget(0, 3)
        self.props.setHorizontalHeaderLabels(["Relação", "Destino", "Certeza"])
        self.props.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.props.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.props.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lp.addWidget(self.props)
        bp = QHBoxLayout()
        for txt, fn in [("Nova proposição", self._nova_prop), ("Editar", self._editar_prop),
                        ("Remover", self._rem_prop)]:
            b = QPushButton(txt); b.clicked.connect(fn); bp.addWidget(b)
        lp.addLayout(bp)
        layout.addWidget(gp, 1)

        # Operações estruturais + fechar
        rod = QHBoxLayout()
        b_merge = QPushButton("Mesclar outro AQUI…")
        b_merge.clicked.connect(self._merge)
        b_split = QPushButton("Desambiguar (split)…")
        b_split.clicked.connect(self._split)
        rod.addWidget(b_merge); rod.addWidget(b_split); rod.addStretch(1)
        fechar = QPushButton("Fechar"); fechar.clicked.connect(self.accept)
        rod.addWidget(fechar)
        layout.addLayout(rod)

    def _carregar(self) -> None:
        try:
            c = self._client.conceito(self._cid)
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e)); return
        self.sentido.setText(c.get("sentido") or "")
        self.rotulos.clear()
        for r in c.get("rotulos", []):
            txt = f"{r['texto']}  ★" if r.get("principal") else r["texto"]
            it = QListWidgetItem(txt); it.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
            self.rotulos.addItem(it)
        self.areas.clear()
        for a in c.get("areas", []):
            it = QListWidgetItem(a["nome"]); it.setData(Qt.ItemDataRole.UserRole, int(a["id"]))
            self.areas.addItem(it)
        self.props.setRowCount(0)
        for p in c.get("proposicoes_origem", []):
            linha = self.props.rowCount(); self.props.insertRow(linha)
            self.props.setItem(linha, 0, QTableWidgetItem(p.get("relacao") or ""))
            dest = p.get("destino", {})
            it_d = QTableWidgetItem(dest.get("rotulo") or "")
            it_d.setData(Qt.ItemDataRole.UserRole, (int(p["proposicao_id"]), int(dest.get("id") or 0)))
            self.props.setItem(linha, 1, it_d)
            self.props.setItem(linha, 2, QTableWidgetItem(str(p.get("fontes_aprovadas", 0))))

    def _executar(self, fn) -> None:
        try:
            fn()
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e)); return
        self._carregar()

    def _salvar_sentido(self) -> None:
        novo = self.sentido.text().strip()
        if novo:
            self._executar(lambda: self._client.editar_conceito(self._cid, novo))

    # rótulos
    def _add_rotulo(self) -> None:
        texto, ok = QInputDialog.getText(self, "Rótulo", "Novo rótulo:")
        if ok and texto.strip():
            self._executar(lambda: self._client.add_rotulo(self._cid, texto.strip()))

    def _principal(self) -> None:
        it = self.rotulos.currentItem()
        if it:
            self._executar(lambda: self._client.rotulo_principal(int(it.data(Qt.ItemDataRole.UserRole))))

    def _rem_rotulo(self) -> None:
        it = self.rotulos.currentItem()
        if it:
            self._executar(lambda: self._client.remover_rotulo(int(it.data(Qt.ItemDataRole.UserRole))))

    # áreas
    def _add_area(self) -> None:
        nome, ok = QInputDialog.getText(self, "Área", "Nome da área:")
        if ok and nome.strip():
            self._executar(lambda: self._client.add_area_conceito(self._cid, nome.strip()))

    def _rem_area(self) -> None:
        it = self.areas.currentItem()
        if it:
            self._executar(lambda: self._client.rem_area_conceito(self._cid, int(it.data(Qt.ItemDataRole.UserRole))))

    # proposições
    def _nova_prop(self) -> None:
        relacao, ok = QInputDialog.getText(self, "Proposição", "Relação (verbo):")
        if not ok or not relacao.strip():
            return
        esc = EscolherConceitoDialog(self._client, self)
        if esc.exec() and esc.escolhido:
            self._executar(lambda: self._client.criar_proposicao(self._cid, relacao.strip(), esc.escolhido))

    def _editar_prop(self) -> None:
        linha = self.props.currentRow()
        if linha < 0:
            return
        prop_id, dest_id = self.props.item(linha, 1).data(Qt.ItemDataRole.UserRole)
        relacao, ok = QInputDialog.getText(self, "Editar proposição", "Relação:",
                                           text=self.props.item(linha, 0).text())
        if not ok or not relacao.strip():
            return
        self._executar(lambda: self._client.editar_proposicao(prop_id, self._cid, relacao.strip(), dest_id))

    def _rem_prop(self) -> None:
        linha = self.props.currentRow()
        if linha < 0:
            return
        prop_id, _ = self.props.item(linha, 1).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Remover", "Remover esta proposição?") == QMessageBox.StandardButton.Yes:
            self._executar(lambda: self._client.remover_proposicao(prop_id))

    # estruturais
    def _merge(self) -> None:
        esc = EscolherConceitoDialog(self._client, self)
        if esc.exec() and esc.escolhido and esc.escolhido != self._cid:
            if QMessageBox.question(
                self, "Mesclar",
                f"Mesclar o conceito #{esc.escolhido} DENTRO de #{self._cid}? (o outro será removido)"
            ) == QMessageBox.StandardButton.Yes:
                self._executar(lambda: self._client.merge_conceito(self._cid, esc.escolhido))

    def _split(self) -> None:
        sentido, ok = QInputDialog.getText(self, "Desambiguar", "Sentido do conceito novo:")
        if not ok or not sentido.strip():
            return
        rot_ids = [int(self.rotulos.item(i).data(Qt.ItemDataRole.UserRole))
                   for i in range(self.rotulos.count()) if self.rotulos.item(i).isSelected()]
        prop_ids = [self.props.item(l, 1).data(Qt.ItemDataRole.UserRole)[0]
                    for l in range(self.props.rowCount())
                    if self.props.item(l, 1) and self.props.item(l, 1).isSelected()]
        self._executar(lambda: self._client.split_conceito(self._cid, sentido.strip(), rot_ids, prop_ids))


class FilaTab(QWidget):
    """Feedback da fila de processamento de documentos (PDF/TXT)."""

    _ICON = {"pendente": "⏳ pendente", "processando": "⚙ processando",
             "processado": "✓ processado", "erro": "⚠ erro"}

    def __init__(self, client: KddClient) -> None:
        super().__init__()
        self._client = client
        self.pode_editar = client.pode_editar()
        layout = QVBoxLayout(self)

        topo = QHBoxLayout()
        self.resumo = QLabel("—")
        topo.addWidget(self.resumo, 1)
        self.chk_auto = QCheckBox("Atualizar automaticamente")
        self.chk_auto.setChecked(True)
        topo.addWidget(self.chk_auto)
        b_at = QPushButton("Atualizar")
        b_at.clicked.connect(self._carregar)
        topo.addWidget(b_at)
        layout.addLayout(topo)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(["ID", "Título", "Processamento", "Aprovação", "Criado em"])
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.itemSelectionChanged.connect(self._atualizar_botoes)
        layout.addWidget(self.tabela, 1)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.b_repro = QPushButton("↻ Reprocessar")
        self.b_repro.setToolTip("Recoloca na fila — apenas fontes com erro.")
        self.b_repro.setEnabled(False)
        self.b_repro.clicked.connect(self._reprocessar)
        acoes.addWidget(self.b_repro)
        if self.pode_editar:
            b_ap = QPushButton("Aprovar fonte")
            b_ap.clicked.connect(lambda: self._moderar(True))
            b_rp = QPushButton("Reprovar fonte")
            b_rp.clicked.connect(lambda: self._moderar(False))
            acoes.addWidget(b_ap)
            acoes.addWidget(b_rp)
        layout.addLayout(acoes)

        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._carregar()

    def _tick(self) -> None:
        if self.chk_auto.isChecked() and self.isVisible():
            self._carregar()

    def _carregar(self) -> None:
        sel = self._sel_id()
        try:
            fontes = self._client.fontes()
        except KddApiError as e:
            self.resumo.setText(f"Erro: {e}")
            return
        cont = {"pendente": 0, "processando": 0, "processado": 0, "erro": 0}
        self.tabela.setRowCount(0)
        for f in fontes:
            proc = f.get("status_proc", "")
            cont[proc] = cont.get(proc, 0) + 1
            r = self.tabela.rowCount()
            self.tabela.insertRow(r)
            id_item = QTableWidgetItem(str(f.get("id")))
            id_item.setData(Qt.ItemDataRole.UserRole, proc)
            self.tabela.setItem(r, 0, id_item)
            self.tabela.setItem(r, 1, QTableWidgetItem(f.get("titulo") or ""))
            self.tabela.setItem(r, 2, QTableWidgetItem(self._ICON.get(proc, proc)))
            self.tabela.setItem(r, 3, QTableWidgetItem(f.get("status_aprovacao") or ""))
            self.tabela.setItem(r, 4, QTableWidgetItem(str(f.get("criado_em") or "")))
            if sel is not None and int(f.get("id")) == sel:
                self.tabela.selectRow(r)
        self.resumo.setText(
            f"{len(fontes)} fonte(s)  ·  ⏳ {cont['pendente']} pendente(s)  ·  "
            f"⚙ {cont['processando']} processando  ·  ✓ {cont['processado']} processado(s)  ·  "
            f"⚠ {cont['erro']} erro(s)")
        self._atualizar_botoes()

    def _sel_id(self) -> int | None:
        r = self.tabela.currentRow()
        if r < 0:
            return None
        it = self.tabela.item(r, 0)
        return int(it.text()) if it else None

    def _atualizar_botoes(self) -> None:
        r = self.tabela.currentRow()
        proc = None
        if r >= 0 and self.tabela.item(r, 0):
            proc = self.tabela.item(r, 0).data(Qt.ItemDataRole.UserRole)
        # só fontes com erro podem ser reprocessadas
        self.b_repro.setEnabled(proc == "erro")

    def _reprocessar(self) -> None:
        fid = self._sel_id()
        if fid is None:
            return
        try:
            self._client.reprocessar_fonte(fid)
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        QMessageBox.information(self, "Reprocessar",
                                f"Fonte #{fid} voltou para a fila (pendente). O bot vai reprocessá-la.")
        self._carregar()

    def _moderar(self, aprovar: bool) -> None:
        fid = self._sel_id()
        if fid is None:
            QMessageBox.information(self, "Fila", "Selecione uma fonte na tabela.")
            return
        try:
            if aprovar:
                self._client.aprovar_fonte(fid)
            else:
                self._client.reprovar_fonte(fid)
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self._carregar()


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
