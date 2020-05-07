# coding=utf-8
import sys
import os
import gc
import pandas as pd
import tqdm
import sqlite3

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import QtGui
from PyQt5 import uic

import creonAPI
import decorators
from pandas_to_pyqt_table import PandasModel
#from creon_datareader_v1_1_ui import Ui_MainWindow
from utils import is_market_open, available_latest_date, preformat_cjk

# .ui 파일에서 직접 클래스 생성하는 경우 주석 해제
Ui_MainWindow = uic.loadUiType("creon_datareader_v1_1.ui")[0]


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.objStockChart = creonAPI.CpStockChart()
        self.objCodeMgr = creonAPI.CpCodeMgr()

        self.rcv_data = dict()  # RQ후 받아온 데이터 저장 멤버
        self.supply_data = dict()  # RQ후 받아온 수급데이터 저장 멤버
        self.update_status_msg = ''  # status bar 에 출력할 메세지 저장 멤버
        self.return_status_msg = ''  # status bar 에 출력할 메세지 저장 멤버

        # timer 등록. tick per 1s
        self.timer_1s = QTimer(self)
        self.timer_1s.start(1000)
        self.timer_1s.timeout.connect(self.timeout_1s)


        # 서버에 존재하는 종목코드 리스트와 로컬DB에 존재하는 종목코드 리스트
        self.sv_code_df = pd.DataFrame()
        self.sv_view_model = None

        # 검색 필터로 필터링된 종목코드 리스트
        self.f_sv_code_df = pd.DataFrame()
        self.f_sv_view_model = None

        self.db_path = ''

        # 'db 경로' 우측 pushButton '연결'이 클릭될 시 실행될 함수 연결
        self.pushButton_2.clicked.connect(self.connect_code_list_view)

        # '종목리스트 경로' pushButton '연결'이 클릭될 시 실행될 함수 연결
        self.pushButton_8.clicked.connect(self.load_code_list)

        # '종목 필터' 오른쪽 lineEdit이 변경될 시 실행될 함수 연결
        self.lineEdit_5.returnPressed.connect(self.filter_code_list_view)

        # pushButton '검색 결과만/전체 다운로드' 이 클릭될 시 실행될 함수 연결
        self.pushButton_3.clicked.connect(self.update_price_db_filtered)
        self.pushButton_4.clicked.connect(self.update_price_db)


    def closeEvent(self, a0: QtGui.QCloseEvent):
        sys.exit()

    def connect_code_list_view(self):
        # 서버 종목 정보 가져와서 dataframe으로 저장
        self.start_range = int(self.lineEdit_10.text())
        self.end_range = int(self.lineEdit_11.text())
        sv_code_list = self.objCodeMgr.get_code_list(1) + self.objCodeMgr.get_code_list(2) + ('U001','U201')
        codes_len = len(sv_code_list)
        sv_code_list = sv_code_list[self.start_range:self.end_range]
        sv_name_list = list(map(self.objCodeMgr.get_code_name, sv_code_list))
        self.sv_code_df = pd.DataFrame({'종목코드': sv_code_list,'종목명': sv_name_list},
                                       columns=('종목코드', '종목명'))

        self.db_path = self.lineEdit_4.text()+'_'+self.lineEdit_10.text()+'_'+self.lineEdit_11.text()+'.db'

        self.sv_view_model = PandasModel(self.sv_code_df)
        self.tableView.setModel(self.sv_view_model)
        self.tableView.resizeColumnToContents(0)

        self.lineEdit_5.setText('')

    def _filter_code_list_view(self, keyword, reset=True):
        # could be improved

        if reset:
            self.f_sv_code_df = pd.DataFrame(columns=('종목코드', '종목명'))
        for i, row in self.sv_code_df.iterrows():
            if keyword in row['종목코드'] + row['종목명']:
                self.f_sv_code_df = self.f_sv_code_df.append(row, ignore_index=True)

        self.f_sv_view_model = PandasModel(self.f_sv_code_df)
        self.tableView.setModel(self.f_sv_view_model)

    # 종목 필터(검색)을 한 뒤 table view를 갱신하는 함수
    def filter_code_list_view(self):
        keyword = self.lineEdit_5.text()
        if len(keyword) == 0:
            self.tableView.setModel(self.sv_view_model)
            return
        self._filter_code_list_view(keyword)

    def timeout_1s(self):
        current_time = QTime.currentTime()

        text_time = current_time.toString("hh:mm:ss")
        time_msg = "현재시간: " + text_time

        if self.return_status_msg == '':
            statusbar_msg = time_msg
        else:
            statusbar_msg = time_msg + " | " + self.update_status_msg + \
                            " | " + self.return_status_msg

        self.statusbar.showMessage(statusbar_msg)

    def load_code_list(self):
        code_list_path = self.lineEdit_8.text()
        code_list = pd.read_csv(code_list_path, dtype=str).values.ravel()
        self._filter_code_list_view(code_list[0], reset=True)
        for code in code_list[1:]:
            self._filter_code_list_view(code, reset=False)

    @decorators.return_status_msg_setter
    def update_price_db(self, filtered=False):
        if filtered:
            fetch_code_df = self.f_sv_code_df
        else:
            fetch_code_df = self.sv_code_df

        count = int(self.lineEdit_9.text())
        if self.radioButton.isChecked(): # 1분봉
            tick_unit = '분봉'
            tick_range = 1
        elif self.radioButton_3.isChecked(): # 5분봉
            tick_unit = '분봉'
            tick_range = 5
        elif self.radioButton_4.isChecked(): # 30분봉
            tick_unit = '분봉'
            tick_range = 30
        else: # 일봉
            tick_unit = '일봉'
            tick_range = 1

        with sqlite3.connect(self.db_path) as con:
            cursor = con.cursor()
            tqdm_range = tqdm.trange(len(fetch_code_df), ncols=100)
            for i in tqdm_range:
                code = fetch_code_df.iloc[i]
                self.update_status_msg = '[{}] {}'.format(code[0], code[1])
                tqdm_range.set_description(preformat_cjk(self.update_status_msg, 25))

                if tick_unit == '일봉':  # 일봉 데이터 받기
                    if self.objStockChart.RequestDWM(code[0], ord('D'), count, self) == False:
                        continue
                elif tick_unit == '분봉':  # 분봉 데이터 받기
                    if self.objStockChart.RequestMT(code[0], ord('m'), tick_range, count, self) == False:
                        continue

                if tick_unit == '일봉':
                    if (code[0] == 'U001' or code[0] == 'U201'):
                        df = pd.DataFrame(self.rcv_data, columns=['priceOpen', 'priceHigh', 'priceLow', 'priceClose', 'volume'],
                                  index=self.rcv_data['logDate'])
                    else:
                        df = pd.DataFrame(self.rcv_data,
                                          columns=['priceOpen', 'priceHigh', 'priceLow', 'priceClose', 'volume', 'amount', 'numListed','marketCap', 'foreignRate','adjRate'],
                                          index=self.rcv_data['logDate'])
                        df2 = pd.DataFrame(self.supply_data, columns=['personNetbuy', 'foreignNetbuy', 'instNetbuy', 'financeNetbuy', 'insuranceNetbuy', 'toosinNetbuy', 'bankNetbuy',
                                            'gitaFinanceNetbuy', 'pensionNetbuy', 'gitaInstNetbuy', 'gitaForeignNetbuy', 'samoNetbuy',
                                            'nationNetbuy'], index=self.supply_data['logDate'])
                        df = df.join(df2)
                else:
                	df = pd.DataFrame(self.rcv_data, columns=['priceOpen', 'priceHigh', 'priceLow', 'priceClose', 'volume', 'amount'],
                                  index=self.rcv_data['logDate'])

                # 뒤집어서 저장 (결과적으로 date 기준 오름차순으로 저장됨)
                df = df.iloc[::-1]
                df = df.iloc[1:]
                df.to_sql(code[0], con, if_exists='replace', index_label='logDate')

                # 메모리 overflow 방지
                del df
                if tick_unit == '일봉' and not (code[0] =='U001' or code[0] =='U201'):
                    del df2
                gc.collect()

        self.update_status_msg = ''
        self.connect_code_list_view()

    def update_price_db_filtered(self):
        self.update_price_db(filtered=True)


app = QApplication


def main():
    global app
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    app.exec_()


if __name__ == "__main__":
    main()