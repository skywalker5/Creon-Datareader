# coding=utf-8
import sys
import os
import gc
import pandas as pd
import sqlite3

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import QtGui
from PyQt5 import uic

import creonAPI
import decorators
from pandas_to_pyqt_table import PandasModel
from creon_datareader_v1_0_ui import Ui_MainWindow

# .ui 파일에서 직접 클래스 생성하는 경우 주석 해제
# Ui_MainWindow = uic.loadUiType("creon_datareader_v0_1.ui")[0]


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.objStockChart = creonAPI.CpStockChart()
        self.objCodeMgr = creonAPI.CpCodeMgr()

        self.rcv_data = dict()  # RQ후 받아온 데이터 저장 멤버
        self.update_status_msg = ''  # status bar 에 출력할 메세지 저장 멤버
        self.return_status_msg = ''  # status bar 에 출력할 메세지 저장 멤버

        # timer 등록. tick per 1s
        self.timer_1s = QTimer(self)
        self.timer_1s.start(1000)
        self.timer_1s.timeout.connect(self.timeout_1s)

        # label '종목코드' 오른쪽 lineEdit 값이 변경 될 시 실행될 함수 연결
        self.lineEdit.textChanged.connect(self.codeEditChanged)

        # pushButton '실행'이 클릭될 시 실행될 함수 연결
        self.pushButton.clicked.connect(self.get_price_db)

        # 서버에 존재하는 종목코드 리스트와 로컬DB에 존재하는 종목코드 리스트
        self.sv_code_df = pd.DataFrame()
        self.db_code_df = pd.DataFrame()
        self.sv_view_model = None
        self.db_view_model = None

        # 검색 필터로 필터링된 종목코드 리스트
        self.f_sv_code_df = pd.DataFrame()
        self.f_db_code_df = pd.DataFrame()
        self.f_sv_view_model = None
        self.f_db_view_model = None

        self.db_path = ''

        # pushButton '연결'이 클릭될 시 실행될 함수 연결
        self.pushButton_2.clicked.connect(self.connect_code_list_view)

        # '종목 필터' 오른쪽 lineEdit이 변경될 시 실행될 함수 연결
        self.lineEdit_5.returnPressed.connect(self.filter_code_list_view)

        # pushButton '검색 결과만/전체 다운로드' 이 클릭될 시 실행될 함수 연결
        self.pushButton_3.clicked.connect(self.update_price_db_filtered)
        self.pushButton_4.clicked.connect(self.update_price_db)


    def closeEvent(self, a0: QtGui.QCloseEvent):
        sys.exit()

    def connect_code_list_view(self):
        # 서버 종목 정보 가져와서 dataframe으로 저장
        sv_code_list = self.objCodeMgr.get_code_list(1) + self.objCodeMgr.get_code_list(2)
        sv_name_list = list(map(self.objCodeMgr.get_code_name, sv_code_list))
        self.sv_code_df = pd.DataFrame({'종목코드': sv_code_list,'종목명': sv_name_list},
                                       columns=('종목코드', '종목명'))

        self.db_path = self.lineEdit_4.text()

        # .db 파일을 새로 생성할 경우에만 radioButton으로 일봉/분봉을 선택할 수 있게 함.
        if not os.path.isfile(self.db_path):
            self.radioButton.setEnabled(True)
            self.radioButton_2.setEnabled(True)

        # 로컬 DB에 저장된 종목 정보 가져와서 dataframe으로 저장
        con = sqlite3.connect(self.db_path)
        cursor = con.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        db_code_list = cursor.fetchall()
        for i in range(len(db_code_list)):
            db_code_list[i] = db_code_list[i][0]
        db_name_list = list(map(self.objCodeMgr.get_code_name, db_code_list))

        db_latest_list = []
        for db_code in db_code_list:
            cursor.execute("SELECT date FROM {} ORDER BY date DESC LIMIT 1".format(db_code))
            db_latest_list.append(cursor.fetchall()[0][0])

        # 현재 db에 저장된 'date' column의 단위(분/일) 확인
        # 한 db 파일에 분봉 데이터와 일봉 데이터가 섞이지 않게 하기 위함
        if db_latest_list:
            self.radioButton.setEnabled(False)
            self.radioButton_2.setEnabled(False)
            # 날짜가 분 단위 인 경우
            if db_latest_list[0] > 99999999:
                self.radioButton.setChecked(True)
            else:
                self.radioButton_2.setChecked(True)

        self.db_code_df = pd.DataFrame(
                {'종목코드': db_code_list, '종목명': db_name_list, '갱신날짜': db_latest_list},
                columns=('종목코드', '종목명', '갱신날짜'))

        self.sv_view_model = PandasModel(self.sv_code_df)
        self.db_view_model = PandasModel(self.db_code_df)
        self.tableView.setModel(self.sv_view_model)
        self.tableView_2.setModel(self.db_view_model)
        self.tableView.resizeColumnToContents(0)
        self.tableView_2.resizeColumnToContents(0)

        self.lineEdit_5.setText('')

    # 종목 필터(검색)을 한 뒤 table view를 갱신하는 함수
    def filter_code_list_view(self):
        keyword = self.lineEdit_5.text()

        if len(keyword) == 0:
            self.tableView.setModel(self.sv_view_model)
            self.tableView_2.setModel(self.db_view_model)
            return

        # could be improved
        self.f_sv_code_df = pd.DataFrame(columns=('종목코드', '종목명'))
        for i, row in self.sv_code_df.iterrows():
            if keyword in row['종목코드'] + row['종목명']:
                self.f_sv_code_df = self.f_sv_code_df.append(row, ignore_index=True)

        self.f_db_code_df = pd.DataFrame(columns=('종목코드', '종목명', '갱신날짜'))
        for i, row in self.db_code_df.iterrows():
            if keyword in row['종목코드'] + row['종목명']:
                self.f_db_code_df = self.f_db_code_df.append(row, ignore_index=True)

        self.f_sv_view_model = PandasModel(self.f_sv_code_df)
        self.f_db_view_model = PandasModel(self.f_db_code_df)
        self.tableView.setModel(self.f_sv_view_model)
        self.tableView_2.setModel(self.f_db_view_model)


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

    # label '종목' 우측의 lineEdit의 이벤트 핸들러
    def codeEditChanged(self):
        code = self.lineEdit.text()

        if len(code) < 6:
            self.lineEdit_2.setText('')
            return

        if not (code[0] == "A"):
            code = "A" + code
            self.lineEdit.setText(code)

        name = self.objCodeMgr.get_code_name(code)
        if len(name) == 0:
            return

        self.lineEdit_2.setText(name)

    # 특정 종목(단일 종목) 데이터 가져오기
    @decorators.return_status_msg_setter
    def get_price_db(self, *args):
        # GUI 에서 인자 가져오기
        code = self.lineEdit.text()
        tick_unit = self.comboBox.currentText()
        tick_range = int(self.comboBox_2.currentText())
        count = int(self.lineEdit_3.text())

        if tick_unit == '일봉':  # 일봉 데이터 받기
            if self.objStockChart.RequestDWM(code, ord('D'), count, self) == False:
                exit()
        elif tick_unit == '분봉':  # 분봉 데이터 받기
            if self.objStockChart.RequestMT(code, ord('m'), tick_range, count, self) == False:
                exit()

        df = pd.DataFrame(self.rcv_data, columns=['open', 'high', 'low', 'close', 'volume'],
                          index=self.rcv_data['date'])
        # 뒤집어서 저장 (결과적으로 date 기준 오름차순으로 저장됨)
        df = df.iloc[::-1]
        with sqlite3.connect("./db/stock_price.db") as con:
            df.to_sql(code, con, if_exists='replace', index_label='date')

    @decorators.return_status_msg_setter
    def update_price_db(self, filtered=False):
        if filtered:
            fetch_code_df = self.f_sv_code_df
        else:
            fetch_code_df = self.sv_code_df

        if self.radioButton.isChecked():
            tick_unit = '분봉'
            count = 200000  # 서버 데이터 최대 reach 약 18.5만 이므로 (18/02/25 기준)
        else:
            tick_unit = '일봉'
            count = 10000  # 10000개면 현재부터 1980년 까지의 데이터에 해당함. 충분.

        tick_range = 1

        with sqlite3.connect(self.db_path) as con:
            cursor = con.cursor()

            for i, code in fetch_code_df.iterrows():
                self.update_status_msg = '[{}/{}]: [{}] {}'.\
                    format(i, len(fetch_code_df), code[0], code[1])
                print(self.update_status_msg)

                from_date = 0
                if code[0] in self.db_code_df['종목코드'].tolist():
                    cursor.execute("SELECT date FROM {} ORDER BY date DESC LIMIT 1".format(code[0]))
                    from_date = cursor.fetchall()[0][0]

                if tick_unit == '일봉':  # 일봉 데이터 받기
                    if self.objStockChart.RequestDWM(code[0], ord('D'), count, self, from_date) == False:
                        exit()
                elif tick_unit == '분봉':  # 분봉 데이터 받기
                    if self.objStockChart.RequestMT(code[0], ord('m'), tick_range, count, self, from_date) == False:
                        exit()

                df = pd.DataFrame(self.rcv_data, columns=['open', 'high', 'low', 'close', 'volume'],
                                  index=self.rcv_data['date'])

                # 기존 DB와 겹치는 부분 제거
                if from_date != 0:
                    df = df.loc[:from_date]
                    df = df.iloc[:-1]

                # 뒤집어서 저장 (결과적으로 date 기준 오름차순으로 저장됨)
                df = df.iloc[::-1]
                df.to_sql(code[0], con, if_exists='append', index_label='date')

                # 메모리 overflow 방지
                del df
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