"""Плавные переходы: снимок старого экрана тает и уходит влево, новый въезжает справа.
Эффект прозрачности накладывается только на снимок, а не на сложные экраны с таблицами —
так анимация лёгкая и не конфликтует со свечением кнопок."""
from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation,
                            QRect, Qt)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QTabWidget

from ui.theme import px

ANIM = {"on": True}          # выключатель «Анимации» в меню
SECTION_MS = 260
TAB_MS = 200


def crossfade(container, old_pixmap, new_widget, ms=TAB_MS, shift=18):
    """container — родитель страниц (стек); old_pixmap — снимок прежней страницы."""
    if not ANIM["on"] or old_pixmap is None or old_pixmap.isNull() or new_widget is None:
        return
    prev = getattr(container, "_anim_cleanup", None)
    if prev:
        prev()
    geo = new_widget.geometry()
    dx = px(shift)

    overlay = QLabel(container)
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    overlay.setPixmap(old_pixmap)
    overlay.setGeometry(geo)
    overlay.raise_()
    overlay.show()
    eff = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(eff)

    fade = QPropertyAnimation(eff, b"opacity")
    fade.setDuration(ms)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    old_move = QPropertyAnimation(overlay, b"pos")
    old_move.setDuration(ms)
    old_move.setStartValue(geo.topLeft())
    old_move.setEndValue(geo.topLeft() - QPoint(dx // 2, 0))
    old_move.setEasingCurve(QEasingCurve.Type.OutCubic)
    new_move = QPropertyAnimation(new_widget, b"pos")
    new_move.setDuration(ms)
    new_move.setStartValue(geo.topLeft() + QPoint(dx, 0))
    new_move.setEndValue(geo.topLeft())
    new_move.setEasingCurve(QEasingCurve.Type.OutCubic)

    group = QParallelAnimationGroup(container)
    for a in (fade, old_move, new_move):
        group.addAnimation(a)

    def cleanup():
        group.stop()
        new_widget.move(geo.topLeft())
        overlay.deleteLater()
        group.deleteLater()           # завершённые анимации не копятся в памяти
        container._anim_cleanup = None

    group.finished.connect(cleanup)
    container._anim_cleanup = cleanup
    group.start()


class AnimatedTabWidget(QTabWidget):
    """Вкладки с плавным переходом. Снимок старой вкладки берётся до переключения:
    при щелчке по вкладке (tabBarClicked) и при программном setCurrentIndex."""

    def __init__(self, *args, ms=TAB_MS):
        super().__init__(*args)
        self._ms = ms
        self._snap = None
        self.tabBar().tabBarClicked.connect(self._remember)
        self.currentChanged.connect(self._animate)

    def _remember(self, index):
        w = self.currentWidget()
        self._snap = w.grab() if (ANIM["on"] and w is not None and self.isVisible()
                                  and index != self.currentIndex()) else None

    def setCurrentIndex(self, index):
        if index != self.currentIndex():
            self._remember(index)
        super().setCurrentIndex(index)

    def _animate(self, index):
        snap, self._snap = self._snap, None
        w = self.currentWidget()
        if snap is not None and w is not None and w.parentWidget() is not None:
            crossfade(w.parentWidget(), snap, w, self._ms)


class NavIndicator:
    """Жёлтая полоска выбранного раздела в меню, плавно переезжающая между пунктами."""

    def __init__(self, nav):
        from PySide6.QtWidgets import QWidget
        self.nav = nav
        self.bar = QWidget(nav.viewport())
        self.bar.setObjectName("navIndicator")
        self.bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.anim = QPropertyAnimation(self.bar, b"geometry")
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        nav.currentRowChanged.connect(lambda *_: self.update(True))

    def target(self):
        item = self.nav.currentItem()
        if item is None:
            return None
        r = self.nav.visualItemRect(item)
        return QRect(0, r.top() + px(6), px(3), r.height() - px(12))

    def update(self, animate=False):
        t = self.target()
        if t is None:
            self.bar.hide()
            return
        self.bar.show()
        self.bar.raise_()
        if animate and ANIM["on"] and self.bar.geometry().height() > 0:
            self.anim.stop()
            self.anim.setStartValue(self.bar.geometry())
            self.anim.setEndValue(t)
            self.anim.start()
        else:
            self.bar.setGeometry(t)
