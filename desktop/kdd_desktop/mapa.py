"""Mapa Conceitual visual (Novak) — canvas QGraphicsView editável.

Conceitos viram nós (caixas com rótulo + sentido, cor por área); proposições viram
setas rotuladas (origem →[relação]→ destino), espessura/cor pela certeza. Layout
HIERÁRQUICO (geral no topo, específico embaixo). Três escopos:
  • Conceito  — a vizinhança de um conceito (navegável por duplo-clique);
  • Documento — todos os conceitos/proposições de uma fonte (PDF);
  • Área      — o mapa de uma área inteira.

Edição (exige token validador): arrastar move nós (posição é salva), "Conectar"
cria proposição arrastando de um nó a outro, botão direito edita/mescla/split/remove.
Zoom com a roda; "Ajustar" enquadra tudo.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .api_client import KddApiError, KddClient

MIN_W, MAX_W = 130.0, 230.0
PAD = 9.0
VGAP, HGAP = 70.0, 36.0   # folgas ENTRE caixas (somadas ao tamanho real de cada uma)
_POS_FILE = Path.home() / ".kdd_map_pos.json"
_FONT_ROT = QFont(); _FONT_ROT.setBold(True); _FONT_ROT.setPointSize(10)
_FONT_SEN = QFont(); _FONT_SEN.setPointSize(8)
_FM_ROT = QFontMetricsF(_FONT_ROT)
_FM_SEN = QFontMetricsF(_FONT_SEN)


def _cor_por_area(area: str) -> QColor:
    """Cor pastel determinística a partir do nome da (primeira) área."""
    if not area:
        return QColor("#e5e7eb")
    h = int(hashlib.md5(area.encode("utf-8")).hexdigest(), 16)
    cor = QColor()
    cor.setHsl(h % 360, 150, 225)
    return cor


def _elide(texto: str, n: int) -> str:
    texto = texto or ""
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def _borda_da_caixa(no: "ConceitoNode", alvo: QPointF) -> QPointF:
    """Ponto na borda da caixa do nó, na direção de ``alvo`` (+2px de folga)."""
    c = no.centro()
    dx, dy = alvo.x() - c.x(), alvo.y() - c.y()
    if dx == 0 and dy == 0:
        return c
    hw, hh = no.w / 2 + 2, no.h / 2 + 2
    sx = hw / abs(dx) if dx else float("inf")
    sy = hh / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return QPointF(c.x() + dx * s, c.y() + dy * s)


class ConceitoNode(QGraphicsItem):
    """Caixa de um conceito: rótulo + sentido, cor por área; arrastável."""

    def __init__(self, cid: int, rotulo: str, sentido: str = "", areas: str = "",
                 foco: bool = False) -> None:
        super().__init__()
        self.cid = cid
        self.rotulo = rotulo or f"#{cid}"
        self.sentido = sentido or ""
        self.areas = areas or ""
        self.foco = foco
        self.edges: list["ProposicaoEdge"] = []
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        tip = self.rotulo + (f" — {self.sentido}" if self.sentido else "")
        if self.areas:
            tip += f"\náreas: {self.areas}"
        self.setToolTip(tip)
        self._medir()

    def _medir(self) -> None:
        """Calcula largura/altura da caixa para o texto caber (com quebra de linha)."""
        larg_texto = max(MIN_W, min(MAX_W, _FM_ROT.horizontalAdvance(self.rotulo) + 2 * PAD))
        cw = larg_texto - 2 * PAD
        flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter)
        self._rot_h = _FM_ROT.boundingRect(QRectF(0, 0, cw, 1000), flags, self.rotulo).height()
        self._sen_h = (_FM_SEN.boundingRect(QRectF(0, 0, cw, 1000), flags,
                       self.sentido).height() if self.sentido else 0.0)
        self.w = larg_texto
        self.h = PAD + self._rot_h + (4 + self._sen_h if self.sentido else 0) + PAD

    def boundingRect(self) -> QRectF:
        return QRectF(-self.w / 2, -self.h / 2, self.w, self.h)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        r = self.boundingRect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        primeira_area = self.areas.split(",")[0].strip() if self.areas else ""
        cor = QColor("#fde68a") if self.foco else _cor_por_area(primeira_area)
        borda = QColor("#b45309") if self.foco else QColor("#475569")
        if self.isSelected():
            borda = QColor("#dc2626")
        painter.setBrush(QBrush(cor))
        painter.setPen(QPen(borda, 2.5 if self.foco else 1.5))
        painter.drawRoundedRect(r, 9, 9)

        flags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
        painter.setFont(_FONT_ROT)
        painter.setPen(QPen(QColor("#111827")))
        painter.drawText(QRectF(r.left() + PAD, r.top() + PAD, r.width() - 2 * PAD, self._rot_h),
                         flags, self.rotulo)
        if self.sentido:
            painter.setFont(_FONT_SEN)
            painter.setPen(QPen(QColor("#374151")))
            painter.drawText(QRectF(r.left() + PAD, r.top() + PAD + self._rot_h + 4,
                                    r.width() - 2 * PAD, self._sen_h), flags, self.sentido)

    def centro(self) -> QPointF:
        return self.scenePos()

    def itemChange(self, change, value):  # noqa: ANN001
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for e in self.edges:
                e.adjust()
        return super().itemChange(change, value)


class ProposicaoEdge(QGraphicsItem):
    """Seta rotulada origem →[relação]→ destino; espessura conforme a certeza."""

    def __init__(self, prop_id: int, origem: ConceitoNode, destino: ConceitoNode,
                 relacao: str, certeza: int = 0) -> None:
        super().__init__()
        self.prop_id = prop_id
        self.origem = origem
        self.destino = destino
        self.relacao = relacao
        self.certeza = certeza
        self._p1 = QPointF()
        self._p2 = QPointF()
        self.setZValue(1)
        origem.edges.append(self)
        destino.edges.append(self)
        self.adjust()

    def adjust(self) -> None:
        self.prepareGeometryChange()
        c1, c2 = self.origem.centro(), self.destino.centro()
        self._p1 = _borda_da_caixa(self.origem, c2)
        self._p2 = _borda_da_caixa(self.destino, c1)

    def boundingRect(self) -> QRectF:
        extra = 80.0
        return QRectF(self._p1, self._p2).normalized().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        largura = 1.5 + min(self.certeza, 6) * 0.9
        cor = QColor("#16a34a") if self.certeza > 0 else QColor("#9ca3af")
        painter.setPen(QPen(cor, largura))
        painter.drawLine(self._p1, self._p2)
        # cabeça da seta
        ang = math.atan2(self._p2.y() - self._p1.y(), self._p2.x() - self._p1.x())
        tam = 12.0
        a = self._p2
        b = QPointF(a.x() - tam * math.cos(ang - math.pi / 7), a.y() - tam * math.sin(ang - math.pi / 7))
        c = QPointF(a.x() - tam * math.cos(ang + math.pi / 7), a.y() - tam * math.sin(ang + math.pi / 7))
        painter.setBrush(QBrush(cor))
        painter.drawPolygon(QPolygonF([a, b, c]))
        # rótulo da relação com fundo legível
        meio = QPointF((self._p1.x() + self._p2.x()) / 2, (self._p1.y() + self._p2.y()) / 2)
        f = painter.font(); f.setPointSize(8); painter.setFont(f)
        txt = _elide(self.relacao, 26)
        larg = painter.fontMetrics().horizontalAdvance(txt) + 8
        cx = QRectF(meio.x() - larg / 2, meio.y() - 9, larg, 16)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.setPen(QPen(QColor("#d1d5db")))
        painter.drawRoundedRect(cx, 4, 4)
        painter.setPen(QPen(QColor("#374151")))
        painter.drawText(cx, Qt.AlignmentFlag.AlignCenter, txt)


class MapaView(QGraphicsView):
    """Canvas: zoom na roda; em 'Conectar', arrastar de um nó a outro cria proposição."""

    def __init__(self, dialog: "MapaDialog") -> None:
        super().__init__()
        self._dlg = dialog
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        self._conectar = False
        self._origem_tmp: ConceitoNode | None = None
        self._linha_tmp: QGraphicsLineItem | None = None
        self._pan = False
        self._pan_ini = None

    def set_modo_conectar(self, on: bool) -> None:
        self._conectar = on
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor if on else Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, ev) -> None:  # noqa: ANN001
        fator = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.scale(fator, fator)

    def _no_em(self, pos) -> ConceitoNode | None:  # noqa: ANN001
        for it in self.items(pos):
            if isinstance(it, ConceitoNode):
                return it
        return None

    def mousePressEvent(self, ev) -> None:  # noqa: ANN001
        if ev.button() == Qt.MouseButton.LeftButton:
            no = self._no_em(ev.pos())
            if self._conectar and no:
                self._origem_tmp = no
                p = no.centro()
                self._linha_tmp = self.scene().addLine(
                    p.x(), p.y(), p.x(), p.y(), QPen(QColor("#dc2626"), 2, Qt.PenStyle.DashLine))
                return
            if not self._conectar and no is None:
                if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Shift+arrastar no vazio = laço de seleção (vários conceitos)
                    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                    super().mousePressEvent(ev)
                    return
                # arrastar o vazio = mover o mapa (pan)
                self._pan = True
                self._pan_ini = ev.pos()
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: ANN001
        if self._linha_tmp and self._origem_tmp:
            p = self._origem_tmp.centro()
            alvo = self.mapToScene(ev.pos())
            self._linha_tmp.setLine(p.x(), p.y(), alvo.x(), alvo.y())
            return
        if self._pan and self._pan_ini is not None:
            d = ev.pos() - self._pan_ini
            self._pan_ini = ev.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: ANN001
        if self._linha_tmp and self._origem_tmp:
            self.scene().removeItem(self._linha_tmp)
            destino = self._no_em(ev.pos())
            origem = self._origem_tmp
            self._linha_tmp = None
            self._origem_tmp = None
            if destino and destino is not origem:
                self._dlg.criar_proposicao(origem.cid, destino.cid)
            return
        if self._pan:
            self._pan = False
            self._pan_ini = None
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        super().mouseReleaseEvent(ev)
        if self.dragMode() == QGraphicsView.DragMode.RubberBandDrag:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)  # encerra o laço; volta ao pan
        self._dlg.salvar_posicoes()  # persiste após arrastar nós

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: ANN001
        no = self._no_em(ev.pos())
        if no:
            self._dlg.focar(no.cid)
            return
        super().mouseDoubleClickEvent(ev)

    def contextMenuEvent(self, ev) -> None:  # noqa: ANN001
        no = self._no_em(ev.pos())
        aresta = next((it for it in self.items(ev.pos()) if isinstance(it, ProposicaoEdge)), None)
        menu = QMenu(self)
        if no:
            menu.addAction("Focar (vizinhança deste conceito)", lambda: self._dlg.focar(no.cid))
            if self._dlg.pode_editar:
                menu.addAction("Editar conceito…", lambda: self._dlg.editar_conceito(no.cid))
                menu.addAction("Mesclar OUTRO aqui…", lambda: self._dlg.mesclar(no.cid))
                menu.addAction("Desambiguar (split)…", lambda: self._dlg.split(no.cid))
        elif aresta and self._dlg.pode_editar:
            menu.addAction("Editar relação…", lambda: self._dlg.editar_relacao(aresta))
            menu.addAction("Remover proposição", lambda: self._dlg.remover_proposicao(aresta.prop_id))
        elif self._dlg.pode_editar:
            menu.addAction("Novo conceito…", self._dlg.novo_conceito)
        if not menu.isEmpty():
            menu.exec(ev.globalPos())


class MapaDialog(QDialog):
    """Mapa conceitual visual, com escopos conceito/documento/área."""

    def __init__(self, client: KddClient, conceito_id: int | None = None, pai=None,  # noqa: ANN001
                 escopo: str | None = None, alvo_id: int | None = None) -> None:
        super().__init__(pai)
        self._client = client
        self.pode_editar = client.pode_editar()
        self._escopo = escopo or "conceito"   # conceito | fonte | area
        self._foco = conceito_id              # id do conceito-foco (escopo conceito)
        self._alvo_id = alvo_id               # id da fonte/área (escopos fonte/area)
        self._nodes: dict[int, ConceitoNode] = {}
        self.setWindowTitle("Mapa Conceitual")
        self.resize(1000, 720)
        self._montar()
        if escopo in ("fonte", "area") and alvo_id:
            idx = {"fonte": 1, "area": 2}[escopo]
            self.cb_escopo.setCurrentIndex(idx)        # popula cb_alvo
            ai = self.cb_alvo.findData(alvo_id)
            if ai >= 0:
                self.cb_alvo.setCurrentIndex(ai)
        elif self._foco:
            self._recarregar()
        else:
            # sem conceito selecionado: abre no escopo Documento (escolhe a 1ª fonte)
            self.cb_escopo.setCurrentIndex(1)

    # ── UI ──
    def _montar(self) -> None:
        layout = QVBoxLayout(self)
        self.view = MapaView(self)
        layout.addWidget(self.view, 1)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Escopo:"))
        self.cb_escopo = QComboBox()
        self.cb_escopo.addItem("Conceito (vizinhança)", "conceito")
        self.cb_escopo.addItem("Documento (fonte)", "fonte")
        self.cb_escopo.addItem("Área", "area")
        self.cb_escopo.currentIndexChanged.connect(self._mudar_escopo)
        barra.addWidget(self.cb_escopo)

        self.cb_alvo = QComboBox()
        self.cb_alvo.setMinimumWidth(260)
        self.cb_alvo.currentIndexChanged.connect(self._mudar_alvo)
        self.cb_alvo.hide()
        barra.addWidget(self.cb_alvo)

        self._b_conectar = QPushButton("🔗 Conectar")
        self._b_conectar.setCheckable(True)
        self._b_conectar.setEnabled(self.pode_editar)
        self._b_conectar.setToolTip("Arraste de um conceito a outro para criar proposição.")
        self._b_conectar.toggled.connect(self.view.set_modo_conectar)
        barra.addWidget(self._b_conectar)

        barra.addWidget(QLabel("<small>Shift+arrastar = selecionar vários</small>"))

        if self.pode_editar:
            b_novo = QPushButton("＋ Conceito")
            b_novo.clicked.connect(self.novo_conceito)
            barra.addWidget(b_novo)

        barra.addStretch(1)
        b_fit = QPushButton("Ajustar")
        b_fit.clicked.connect(self._ajustar)
        barra.addWidget(b_fit)
        b_at = QPushButton("Atualizar")
        b_at.clicked.connect(self._recarregar)
        barra.addWidget(b_at)
        layout.addLayout(barra)

    def _mudar_escopo(self) -> None:
        self._escopo = self.cb_escopo.currentData()
        self.cb_alvo.blockSignals(True)
        self.cb_alvo.clear()
        if self._escopo == "fonte":
            for f in self._client.fontes():
                self.cb_alvo.addItem(f"#{f['id']} — {f.get('titulo') or ''}", int(f["id"]))
            self.cb_alvo.show()
        elif self._escopo == "area":
            for a in _achatar_areas(self._client.areas()):
                self.cb_alvo.addItem(a["nome"], a["id"])
            self.cb_alvo.show()
        else:
            self.cb_alvo.hide()
        self.cb_alvo.blockSignals(False)
        if self._escopo in ("fonte", "area") and self.cb_alvo.count():
            self._alvo_id = self.cb_alvo.currentData()
        self._recarregar()

    def _mudar_alvo(self) -> None:
        self._alvo_id = self.cb_alvo.currentData()
        self._recarregar()

    # ── carga + layout ──
    def focar(self, conceito_id: int) -> None:
        if self._escopo != "conceito":
            self.cb_escopo.setCurrentIndex(0)  # dispara _mudar_escopo
        self._escopo = "conceito"
        self._foco = conceito_id
        self._recarregar()

    def _coletar(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int | None, str]:
        """Retorna (conceitos, proposicoes, foco_id, titulo) conforme o escopo."""
        if self._escopo == "fonte" and self._alvo_id:
            d = self._client.fonte_mapa(self._alvo_id)
            return d.get("conceitos", []), d.get("proposicoes", []), None, \
                f"Documento: {d.get('fonte', {}).get('titulo', '')}"
        if self._escopo == "area" and self._alvo_id:
            conc = self._client.conceitos(area=self._alvo_id)
            conceitos = [{"id": c["id"], "rotulo": (c.get("rotulos") or "").split(",")[0].strip(),
                          "sentido": c.get("sentido") or "", "areas": c.get("areas") or ""} for c in conc]
            ids = {c["id"] for c in conceitos}
            props = [p for p in self._client.proposicoes()
                     if p["origem"]["id"] in ids and p["destino"]["id"] in ids]
            nome = self.cb_alvo.currentText() if self.cb_alvo.count() else ""
            return conceitos, props, None, f"Área: {nome}"
        # escopo conceito (vizinhança)
        if not self._foco:
            return [], [], None, ""
        c = self._client.conceito(self._foco)
        if not c:
            return [], [], None, ""
        rot = _rotulo_principal(c)
        areas = ", ".join(a["nome"] for a in c.get("areas", []))
        conceitos = [{"id": self._foco, "rotulo": rot, "sentido": c.get("sentido") or "", "areas": areas}]
        props: list[dict[str, Any]] = []
        for p in c.get("proposicoes_origem", []):
            o = p["destino"]
            conceitos.append({"id": o["id"], "rotulo": o.get("rotulo") or "", "sentido": "", "areas": ""})
            props.append({"id": p["proposicao_id"], "relacao": p["relacao"],
                          "origem": {"id": self._foco}, "destino": {"id": o["id"]},
                          "fontes_aprovadas": p.get("fontes_aprovadas", 0)})
        for p in c.get("proposicoes_destino", []):
            o = p["origem"]
            conceitos.append({"id": o["id"], "rotulo": o.get("rotulo") or "", "sentido": "", "areas": ""})
            props.append({"id": p["proposicao_id"], "relacao": p["relacao"],
                          "origem": {"id": o["id"]}, "destino": {"id": self._foco},
                          "fontes_aprovadas": p.get("fontes_aprovadas", 0)})
        return conceitos, props, self._foco, f"Conceito: {rot}"

    def _recarregar(self) -> None:
        try:
            conceitos, props, foco_id, titulo = self._coletar()
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return

        cena = QGraphicsScene(self)
        self.view.setScene(cena)
        self._nodes = {}

        # dedup conceitos por id
        vistos: dict[int, dict[str, Any]] = {}
        for c in conceitos:
            cid = int(c["id"])
            if cid not in vistos or (not vistos[cid].get("sentido") and c.get("sentido")):
                vistos[cid] = c

        for cid, c in vistos.items():
            no = ConceitoNode(cid, c.get("rotulo") or f"#{cid}", c.get("sentido") or "",
                              c.get("areas") or "", foco=(cid == foco_id))
            cena.addItem(no)
            self._nodes[cid] = no

        edges_ids: list[tuple[int, int]] = []
        for p in props:
            oid, did = int(p["origem"]["id"]), int(p["destino"]["id"])
            if oid in self._nodes and did in self._nodes:
                cena.addItem(ProposicaoEdge(int(p.get("id") or 0), self._nodes[oid],
                                            self._nodes[did], p.get("relacao") or "",
                                            int(p.get("fontes_aprovadas") or 0)))
                edges_ids.append((oid, did))

        self._posicionar(edges_ids, foco_id)
        self.view.set_modo_conectar(self._b_conectar.isChecked())
        cena.setSceneRect(cena.itemsBoundingRect().adjusted(-100, -100, 100, 100))
        self._ajustar()
        n_c, n_p = len(self._nodes), len(edges_ids)
        self.setWindowTitle(f"Mapa Conceitual — {titulo}  ({n_c} conceitos, {n_p} proposições)")

    def _posicionar(self, edges: list[tuple[int, int]], foco_id: int | None) -> None:
        salvos = self._pos_salvas()
        sizes = {cid: (no.w, no.h) for cid, no in self._nodes.items()}
        layout = _layout_hierarquico(list(self._nodes.keys()), edges, sizes)
        for cid, no in self._nodes.items():
            if str(cid) in salvos:
                x, y = salvos[str(cid)]
            else:
                x, y = layout.get(cid, (0.0, 0.0))
            no.setPos(x, y)
        for no in self._nodes.values():
            for e in no.edges:
                e.adjust()

    def _ajustar(self) -> None:
        r = self.view.scene().itemsBoundingRect()
        if not r.isEmpty():
            self.view.fitInView(r.adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)

    # ── posições persistidas ──
    def _chave_pos(self) -> str:
        alvo = self._foco if self._escopo == "conceito" else self._alvo_id
        return f"{self._escopo}:{alvo}"

    def _pos_salvas(self) -> dict[str, list[float]]:
        try:
            todas = json.loads(_POS_FILE.read_text(encoding="utf-8")) if _POS_FILE.is_file() else {}
        except (OSError, ValueError):
            return {}
        return todas.get(self._chave_pos(), {})

    def salvar_posicoes(self) -> None:
        try:
            todas = json.loads(_POS_FILE.read_text(encoding="utf-8")) if _POS_FILE.is_file() else {}
        except (OSError, ValueError):
            todas = {}
        todas[self._chave_pos()] = {
            str(cid): [no.scenePos().x(), no.scenePos().y()] for cid, no in self._nodes.items()
        }
        try:
            _POS_FILE.write_text(json.dumps(todas, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ── operações de edição (chamam a API e recarregam) ──
    def _exec(self, fn) -> None:  # noqa: ANN001
        try:
            fn()
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self._recarregar()

    def criar_proposicao(self, origem_id: int, destino_id: int) -> None:
        relacao, ok = QInputDialog.getText(self, "Nova proposição", "Relação (verbo):")
        if ok and relacao.strip():
            self._exec(lambda: self._client.criar_proposicao(origem_id, relacao.strip(), destino_id))

    def editar_relacao(self, aresta: ProposicaoEdge) -> None:
        relacao, ok = QInputDialog.getText(self, "Editar relação", "Relação:", text=aresta.relacao)
        if ok and relacao.strip():
            self._exec(lambda: self._client.editar_proposicao(
                aresta.prop_id, aresta.origem.cid, relacao.strip(), aresta.destino.cid))

    def remover_proposicao(self, prop_id: int) -> None:
        if QMessageBox.question(self, "Remover", "Remover esta proposição?") == QMessageBox.StandardButton.Yes:
            self._exec(lambda: self._client.remover_proposicao(prop_id))

    def novo_conceito(self) -> None:
        sentido, ok = QInputDialog.getText(self, "Novo conceito", "Sentido:")
        if not ok or not sentido.strip():
            return
        rotulo, ok = QInputDialog.getText(self, "Novo conceito", "Rótulo principal:")
        if not ok or not rotulo.strip():
            return
        self._exec(lambda: self._client.criar_conceito(sentido.strip(), rotulo.strip(), []))

    def editar_conceito(self, cid: int) -> None:
        from .app import ConceitoEditorDialog
        ConceitoEditorDialog(self._client, cid, self).exec()
        self._recarregar()

    def mesclar(self, alvo_id: int) -> None:
        from .app import EscolherConceitoDialog
        esc = EscolherConceitoDialog(self._client, self)
        if esc.exec() and esc.escolhido and esc.escolhido != alvo_id:
            if QMessageBox.question(
                self, "Mesclar",
                f"Mesclar #{esc.escolhido} DENTRO de #{alvo_id}? (o outro será removido)"
            ) == QMessageBox.StandardButton.Yes:
                self._exec(lambda: self._client.merge_conceito(alvo_id, esc.escolhido))

    def split(self, cid: int) -> None:
        sentido, ok = QInputDialog.getText(self, "Desambiguar", "Sentido do conceito novo:")
        if ok and sentido.strip():
            self._exec(lambda: self._client.split_conceito(cid, sentido.strip(), [], []))


class MapasDialog(QDialog):
    """Lista de Mapas — cada mapa tem um título. Documentos (fontes) e Áreas."""

    def __init__(self, client: KddClient, pai=None) -> None:  # noqa: ANN001
        super().__init__(pai)
        self._client = client
        self.setWindowTitle("Mapas")
        self.resize(720, 540)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Mapas</b> — duplo-clique para abrir"))

        from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem
        self._ListWidgetItem = QListWidgetItem

        self.busca = QLineEdit(placeholderText="Filtrar mapas por título…")
        self.busca.textChanged.connect(self._filtrar)
        layout.addWidget(self.busca)

        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(self._abrir_item)
        layout.addWidget(self.lista, 1)

        barra = QHBoxLayout()
        barra.addStretch(1)
        b_abrir = QPushButton("Abrir mapa")
        b_abrir.clicked.connect(self._abrir_selecionado)
        at = QPushButton("Atualizar")
        at.clicked.connect(self._carregar)
        barra.addWidget(at)
        barra.addWidget(b_abrir)
        layout.addLayout(barra)
        self._carregar()

    def _carregar(self) -> None:
        try:
            fontes = self._client.fontes()
            areas = _achatar_areas(self._client.areas())
            const = {a["id"]: a["conceitos"] for a in self._client.constelacao().get("areas", [])}
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.lista.clear()
        # Mapas de documento (título = título da fonte)
        for f in fontes:
            titulo = f.get("titulo") or f"Fonte #{f['id']}"
            proc = f.get("status_proc", "")
            marca = {"pendente": "⏳", "processando": "⚙", "processado": "", "erro": "⚠"}.get(proc, "")
            it = self._ListWidgetItem(f"📄  {titulo}  {marca}".rstrip())
            it.setData(Qt.ItemDataRole.UserRole, ("fonte", int(f["id"])))
            it.setToolTip(f"Documento (fonte #{f['id']}) · proc: {proc} · {f.get('status_aprovacao', '')}")
            self.lista.addItem(it)
        # Mapas de área (título = nome da área)
        for a in areas:
            n = const.get(a["id"], 0)
            it = self._ListWidgetItem(f"🗂  {a['nome']}  ({n} conceito(s))")
            it.setData(Qt.ItemDataRole.UserRole, ("area", a["id"]))
            it.setToolTip("Mapa da área")
            self.lista.addItem(it)
        self._filtrar(self.busca.text())

    def _filtrar(self, texto: str) -> None:
        t = (texto or "").strip().lower()
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _abrir_item(self, item) -> None:  # noqa: ANN001
        escopo, alvo = item.data(Qt.ItemDataRole.UserRole)
        MapaDialog(self._client, escopo=escopo, alvo_id=alvo, pai=self).exec()

    def _abrir_selecionado(self) -> None:
        if self.lista.currentItem():
            self._abrir_item(self.lista.currentItem())


class MapasTab(QWidget):
    """Aba Mapas: lista de mapas à esquerda; conceitos do mapa selecionado à direita."""

    def __init__(self, client: KddClient, pai=None) -> None:  # noqa: ANN001
        super().__init__(pai)
        self._client = client
        layout = QVBoxLayout(self)
        split = QSplitter()
        layout.addWidget(split, 1)

        # Esquerda: filtro + lista de mapas
        esq = QWidget(); le = QVBoxLayout(esq); le.setContentsMargins(0, 0, 0, 0)
        self.busca = QLineEdit(placeholderText="Filtrar mapas por título…")
        self.busca.textChanged.connect(self._filtrar)
        self.lst_mapas = QListWidget()
        self.lst_mapas.currentItemChanged.connect(self._mapa_selecionado)
        self.lst_mapas.itemDoubleClicked.connect(self._abrir_visual)
        le.addWidget(QLabel("<b>Mapas</b>"))
        le.addWidget(self.busca)
        le.addWidget(self.lst_mapas, 1)
        b_at = QPushButton("Atualizar")
        b_at.clicked.connect(self._carregar)
        le.addWidget(b_at)
        split.addWidget(esq)

        # Direita: conceitos do mapa selecionado
        dir_ = QWidget(); ld = QVBoxLayout(dir_); ld.setContentsMargins(0, 0, 0, 0)
        self.lbl = QLabel("<b>Conceitos do mapa</b>")
        self.lst_conceitos = QListWidget()
        ld.addWidget(self.lbl)
        ld.addWidget(self.lst_conceitos, 1)
        self.b_visual = QPushButton("Abrir no mapa visual")
        self.b_visual.clicked.connect(lambda: self._abrir_visual(self.lst_mapas.currentItem()))
        self.b_visual.setEnabled(False)
        ld.addWidget(self.b_visual)
        split.addWidget(dir_)
        split.setSizes([320, 540])

        self._carregar()

    def _carregar(self) -> None:
        try:
            fontes = self._client.fontes()
            areas = _achatar_areas(self._client.areas())
            const = {a["id"]: a["conceitos"] for a in self._client.constelacao().get("areas", [])}
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.lst_mapas.clear()
        for f in fontes:
            proc = f.get("status_proc", "")
            marca = {"pendente": "⏳", "processando": "⚙", "erro": "⚠"}.get(proc, "")
            it = QListWidgetItem(f"📄  {f.get('titulo') or ('Fonte #' + str(f['id']))}  {marca}".rstrip())
            it.setData(Qt.ItemDataRole.UserRole, ("fonte", int(f["id"])))
            self.lst_mapas.addItem(it)
        for a in areas:
            it = QListWidgetItem(f"🗂  {a['nome']}  ({const.get(a['id'], 0)})")
            it.setData(Qt.ItemDataRole.UserRole, ("area", a["id"]))
            self.lst_mapas.addItem(it)
        self._filtrar(self.busca.text())

    def _filtrar(self, texto: str) -> None:
        t = (texto or "").strip().lower()
        for i in range(self.lst_mapas.count()):
            it = self.lst_mapas.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _mapa_selecionado(self, item, _ant=None) -> None:  # noqa: ANN001
        self.lst_conceitos.clear()
        self.b_visual.setEnabled(item is not None)
        if item is None:
            self.lbl.setText("<b>Conceitos do mapa</b>")
            return
        escopo, alvo = item.data(Qt.ItemDataRole.UserRole)
        try:
            conceitos = self._conceitos_do_mapa(escopo, alvo)
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        titulo = item.text().split("  ")[0] + "  " + " ".join(item.text().split("  ")[1:]).strip()
        self.lbl.setText(f"<b>Conceitos do mapa</b> — {len(conceitos)}")
        for c in conceitos:
            rot = c.get("rotulo") or f"#{c['id']}"
            sent = c.get("sentido") or ""
            it = QListWidgetItem(f"{rot}" + (f" — {_elide(sent, 60)}" if sent else ""))
            it.setData(Qt.ItemDataRole.UserRole, int(c["id"]))
            it.setToolTip(sent)
            self.lst_conceitos.addItem(it)

    def _conceitos_do_mapa(self, escopo: str, alvo: int) -> list[dict[str, Any]]:
        if escopo == "fonte":
            return self._client.fonte_mapa(alvo).get("conceitos", [])
        conc = self._client.conceitos(area=alvo)
        return [{"id": c["id"], "rotulo": (c.get("rotulos") or "").split(",")[0].strip(),
                 "sentido": c.get("sentido") or ""} for c in conc]

    def _abrir_visual(self, item) -> None:  # noqa: ANN001
        if not item:
            return
        escopo, alvo = item.data(Qt.ItemDataRole.UserRole)
        MapaDialog(self._client, escopo=escopo, alvo_id=alvo, pai=self).exec()


def _layout_hierarquico(
    ids: list[int], edges: list[tuple[int, int]],
    sizes: dict[int, tuple[float, float]] | None = None,
) -> dict[int, tuple[float, float]]:
    """Layout em camadas (Novak) com anti-colisão.

    1) rank por caminho mais longo (Kahn); 2) ordena cada camada por baricentro
    dos vizinhos (reduz cruzamentos de arestas); 3) empacota X usando a largura
    REAL de cada caixa + folga; 4) Y por altura acumulada das camadas.
    """
    sizes = sizes or {}

    def w(n: int) -> float:
        return sizes.get(n, (MIN_W, 0.0))[0]

    def h(n: int) -> float:
        return sizes.get(n, (0.0, 64.0))[1]

    succ: dict[int, list[int]] = defaultdict(list)
    pred: dict[int, list[int]] = defaultdict(list)
    indeg: dict[int, int] = {n: 0 for n in ids}
    vistos: set[tuple[int, int]] = set()
    for o, d in edges:
        if o in indeg and d in indeg and o != d and (o, d) not in vistos:
            succ[o].append(d)
            pred[d].append(o)
            indeg[d] += 1
            vistos.add((o, d))

    rank: dict[int, int] = {n: 0 for n in ids}
    grau = dict(indeg)
    fila = deque([n for n in ids if grau[n] == 0])
    while fila:
        u = fila.popleft()
        for v in succ[u]:
            rank[v] = max(rank[v], rank[u] + 1)
            grau[v] -= 1
            if grau[v] == 0:
                fila.append(v)

    camadas_idx: dict[int, list[int]] = defaultdict(list)
    for n in ids:
        camadas_idx[rank[n]].append(n)
    ranks = sorted(camadas_idx)
    ordem = {r: list(camadas_idx[r]) for r in ranks}

    def empacotar(r: int) -> dict[int, float]:
        linha = ordem[r]
        total = sum(w(n) for n in linha) + HGAP * max(len(linha) - 1, 0)
        x = -total / 2
        xs: dict[int, float] = {}
        for n in linha:
            xs[n] = x + w(n) / 2
            x += w(n) + HGAP
        return xs

    xpos = {n: x for r in ranks for n, x in empacotar(r).items()}

    # passes de baricentro (alternando direção) para reduzir cruzamentos
    for passo in range(4):
        seq = ranks if passo % 2 == 0 else list(reversed(ranks))
        for r in seq:
            viz = pred if passo % 2 == 0 else succ
            def bary(n: int) -> float:
                vs = viz[n]
                return sum(xpos[v] for v in vs) / len(vs) if vs else xpos[n]
            ordem[r].sort(key=bary)
            for n, x in empacotar(r).items():
                xpos[n] = x

    pos: dict[int, tuple[float, float]] = {}
    y = 0.0
    for r in ranks:
        alt = max((h(n) for n in ordem[r]), default=64.0)
        for n in ordem[r]:
            pos[n] = (xpos[n], y + alt / 2)
        y += alt + VGAP
    return pos


def _achatar_areas(arvore: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Achata a árvore de áreas (id, nome) numa lista ordenada por nome."""
    out: list[dict[str, Any]] = []

    def visita(no: dict[str, Any]) -> None:
        out.append({"id": no["id"], "nome": no["nome"]})
        for f in no.get("filhos", []):
            visita(f)

    for raiz in arvore:
        visita(raiz)
    out.sort(key=lambda a: a["nome"])
    return out


def _rotulo_principal(c: dict[str, Any]) -> str:
    rotulos = c.get("rotulos", [])
    for r in rotulos:
        if r.get("principal"):
            return r["texto"]
    return rotulos[0]["texto"] if rotulos else (c.get("sentido") or f"#{c.get('id')}")
