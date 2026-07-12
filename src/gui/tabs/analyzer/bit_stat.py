from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QFrame

class BitStatTab(QFrame):
    def __init__(self):
         super().__init__() 
         self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        bit_stat_label = QLabel("Bit Stat Tab will be here!") 
        main_layout.addWidget(bit_stat_label)
    