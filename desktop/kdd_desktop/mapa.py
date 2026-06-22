"""Mapa Conceitual visual (Novak) — canvas QGraphicsView editável.

Conceitos viram nós (caixas); proposições viram setas rotuladas (origem →[relação]→
destino), com a espessura proporcional à certeza. É um editor: arrastar move nós,
puxar do nó em "modo conectar" cria proposição, duplo-clique re-centra o mapa no nó,
botão direito abre operações (editar, mesclar, desambiguar, remover).

Usa os endpoints do editor já existentes via KddClient. Edição exige token validador.
"""
from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .api_client import KddApiError, KddClient

NODE_W, NODE_H = 150.0, 54.0


class ConceitoNode(QGraphicsItem):
    """Caixa de um conceito; arrastável, guarda suas arestas para reposicioná-las."""

    def __init__(self, cid: int, rotulo: str, sentido: str = "", foco: bool = False) -> None:
        super().__init__()
        self.cid = cid
        self.rotulo = rotulo or f"#{cid}"
        self.sentido = sentido
        self.foco = foco
        self.edges: list["ProposicaoEdge"] = []
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        if sentido:
            self.setToolTip(f"{rotulo} — {sentido}")

    def boundingRect(self) -> QRectF:
        return QRectF(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        r = self.boundingRect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cor = QColor("#fde68a") if self.foco else QColor("#e0e7ff")
        borda = QColor("#b45309") if self.foco else QColor("#4338ca")
        if self.isSelected():
            borda = QColor("#dc2626")
        painter.setBrush(QBrush(cor))
        painter.setPen(QPen(borda, 2))
        painter.drawRoundedRect(r, 8, 8)
        painter.setPen(QPen(QColor("#111827")))
        texto = self.rotulo if len(self.rotulo) <= 30 else self.rotulo[:29] + "…"
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, texto)

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
        self.setAcceptedMouseButtons(Qt.MouseButton.AllButtons)
        origem.edges.append(self)
        destino.edges.append(self)
        self.adjust()

    def adjust(self) -> None:
        self.prepareGeometryChange()
        c1, c2 = self.origem.centro(), self.destino.centro()
        ang = math.atan2(c2.y() - c1.y(), c2.x() - c1.x())
        # encosta as pontas na borda das caixas
        off = QPointF(math.cos(ang) * (NODE_W / 2 + 2), math.sin(ang) * (NODE_H / 2 + 2))
        self._p1 = c1 + off
        self._p2 = c2 - off

    def boundingRect(self) -> QRectF:
        extra = 24.0
        return QRectF(self._p1, self._p2).normalized().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        largura = 1.5 + min(self.certeza, 6) * 0.9
        cor = QColor("#16a34a") if self.certeza > 0 else QColor("#9ca3af")
        painter.setPen(QPen(cor, largura))
        painter.drawLine(self._p1, self._p2)
        # cabeça da seta
        ang = math.atan2(self._p2.y() - self._p1.y(), self._p2.x() - self._p1.x())
        tam = 11.0
        a = self._p2
        b = QPointF(a.x() - tam * math.cos(ang - math.pi / 7), a.y() - tam * math.sin(ang - math.pi / 7))
        c = QPointF(a.x() - tam * math.cos(ang + math.pi / 7), a.y() - tam * math.sin(ang + math.pi / 7))
        painter.setBrush(QBrush(cor))
        painter.drawPolygon(QPolygonF([a, b, c]))
        # rótulo da relação no meio
        meio = QPointF((self._p1.x() + self._p2.x()) / 2, (self._p1.y() + self._p2.y()) / 2)
        painter.setPen(QPen(QColor("#374151")))
        rot = f"{self.relacao}  ({self.certeza})"
        painter.drawText(meio + QPointF(4, -4), rot)


class MapaView(QGraphicsView):
    """Canvas. Em 'modo conectar', arrastar de um nó a outro cria proposição."""

    def __init__(self, dialog: "MapaDialog") -> None:
        super().__init__()
        self._dlg = dialog
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._conectar = False
        self._origem_tmp: ConceitoNode | None = None
        self._linha_tmp: QGraphicsLineItem | None = None

    def set_modo_conectar(self, on: bool) -> None:
        self._conectar = on
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if on else QGraphicsView.DragMode.RubberBandDrag
        )

    def _no_em(self, pos) -> ConceitoNode | None:  # noqa: ANN001
        for it in self.items(pos):
            if isinstance(it, ConceitoNode):
                return it
        return None

    def mousePressEvent(self, ev) -> None:  # noqa: ANN001
        if self._conectar and ev.button() == Qt.MouseButton.LeftButton:
            no = self._no_em(ev.pos())
            if no:
                self._origem_tmp = no
                p = no.centro()
                self._linha_tmp = self.scene().addLine(p.x(), p.y(), p.x(), p.y(),
                                                        QPen(QColor("#dc2626"), 2, Qt.PenStyle.DashLine))
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: ANN001
        if self._linha_tmp and self._origem_tmp:
            p = self._origem_tmp.centro()
            alvo = self.mapToScene(ev.pos())
            self._linha_tmp.setLine(p.x(), p.y(), alvo.x(), alvo.y())
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
        super().mouseReleaseEvent(ev)

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
            menu.addAction("Focar neste conceito", lambda: self._dlg.focar(no.cid))
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
    """Janela do mapa conceitual de um conceito-foco e sua vizinhança."""

    def __init__(self, client: KddClient, conceito_id: int, pai=None) -> None:  # noqa: ANN001
        super().__init__(pai)
        self._client = client
        self.pode_editar = client.pode_editar()
        self._foco = conceito_id
        self.setWindowTitle("Mapa Conceitual")
        self.resize(900, 680)

        layout = QVBoxLayout(self)
        self.view = MapaView(self)
        layout.addWidget(self.view, 1)

        from PySide6.QtWidgets import QHBoxLayout
        barra = QHBoxLayout()
        self._b_conectar = QPushButton("🔗 Conectar (criar proposição)")
        self._b_conectar.setCheckable(True)
        self._b_conectar.setEnabled(self.pode_editar)
        self._b_conectar.toggled.connect(self.view.set_modo_conectar)
        atualizar = QPushButton("Atualizar")
        atualizar.clicked.connect(self._recarregar)
        barra.addWidget(self._b_conectar)
        if self.pode_editar:
            b_novo = QPushButton("＋ Conceito")
            b_novo.clicked.connect(self.novo_conceito)
            barra.addWidget(b_novo)
        barra.addStretch(1)
        barra.addWidget(atualizar)
        layout.addLayout(barra)

        self._recarregar()

    # ── carga e layout ──
    def focar(self, conceito_id: int) -> None:
        self._foco = conceito_id
        self._recarregar()

    def _recarregar(self) -> None:
        try:
            c = self._client.conceito(self._foco)
        except KddApiError as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        if not c:
            QMessageBox.information(self, "Mapa", "Conceito não encontrado.")
            return

        cena = QGraphicsScene(self)
        self.view.setScene(cena)

        rot_foco = _rotulo_principal(c)
        foco = ConceitoNode(self._foco, rot_foco, c.get("sentido") or "", foco=True)
        cena.addItem(foco)
        foco.setPos(0, 0)
        nos: dict[int, ConceitoNode] = {self._foco: foco}

        vizinhos: list[tuple[dict[str, Any], bool]] = []
        for p in c.get("proposicoes_origem", []):
            vizinhos.append((p, True))
        for p in c.get("proposicoes_destino", []):
            vizinhos.append((p, False))

        n = max(len(vizinhos), 1)
        raio = 280.0
        for i, (p, saindo) in enumerate(vizinhos):
            ang = (2 * math.pi * i) / n - math.pi / 2
            outro = p.get("destino" if saindo else "origem", {})
            oid = int(outro.get("id") or 0)
            if oid and oid not in nos:
                no = ConceitoNode(oid, outro.get("rotulo") or f"#{oid}")
                cena.addItem(no)
                no.setPos(raio * math.cos(ang), raio * math.sin(ang))
                nos[oid] = no
            origem_no = foco if saindo else nos.get(oid)
            destino_no = nos.get(oid) if saindo else foco
            if origem_no and destino_no:
                cena.addItem(ProposicaoEdge(
                    int(p.get("proposicao_id") or 0), origem_no, destino_no,
                    p.get("relacao") or "", int(p.get("fontes_aprovadas") or 0)))

        self.view.set_modo_conectar(self._b_conectar.isChecked())
        cena.setSceneRect(cena.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self.setWindowTitle(f"Mapa Conceitual — {rot_foco} (#{self._foco})")

    # ── operações (chamam a API e recarregam) ──
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


def _rotulo_principal(c: dict[str, Any]) -> str:
    rotulos = c.get("rotulos", [])
    for r in rotulos:
        if r.get("principal"):
            return r["texto"]
    return rotulos[0]["texto"] if rotulos else (c.get("sentido") or f"#{c.get('id')}")
