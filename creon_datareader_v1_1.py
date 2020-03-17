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
from creon_datareader_v1_1_ui import Ui_MainWindow
from utils import is_market_open, available_latest_date, preformat_cjk

# .ui 파일에서 직접 클래스 생성하는 경우 주석 해제
# Ui_MainWindow = uic.loadUiType("creon_datareader_v0_1.ui")[0]


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
        self.db_code_df = pd.DataFrame()
        self.sv_view_model = None
        self.db_view_model = None

        # 검색 필터로 필터링된 종목코드 리스트
        self.f_sv_code_df = pd.DataFrame()
        self.f_db_code_df = pd.DataFrame()
        self.f_sv_view_model = None
        self.f_db_view_model = None

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
        sv_code_list = self.objCodeMgr.get_code_list(1) + self.objCodeMgr.get_code_list(2) + ('U001','U201')
        sv_name_list = list(map(self.objCodeMgr.get_code_name, sv_code_list))
        self.sv_code_df = pd.DataFrame({'종목코드': sv_code_list,'종목명': sv_name_list},
                                       columns=('종목코드', '종목명'))

        self.db_path = self.lineEdit_4.text()

        # .db 파일을 새로 생성할 경우에만 radioButton으로 1분/5분/일봉/.. 을 선택할 수 있게 함.
        if not os.path.isfile(self.db_path):
            self.radioButton.setEnabled(True)
            self.radioButton_2.setEnabled(True)
            self.radioButton_3.setEnabled(True)
            self.radioButton_4.setEnabled(True)
            self.radioButton_5.setEnabled(True)

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
            cursor.execute("SELECT date FROM {} ORDER BY date ASC LIMIT 2".format(db_code_list[0]))
            date0, date1 = cursor.fetchall()
            self.radioButton.setEnabled(False)
            self.radioButton_2.setEnabled(False)
            self.radioButton_3.setEnabled(False)
            self.radioButton_4.setEnabled(False)
            self.radioButton_5.setEnabled(False)

            # 날짜가 분 단위 인 경우
            if date0[0] > 99999999:
                if date1[0] - date0[0] == 5: # 5분 간격인 경우
                    self.radioButton_3.setChecked(True)
                else: # 1분 간격인 경우

                    self.radioButton.setChecked(True)
            elif date0[0]%100 == 0: # 월봉인 경우
                self.radioButton_5.setChecked(True)
            elif date0[0]%10 == 0: # 주봉인 경우
                self.radioButton_4.setChecked(True)
            else: # 일봉인 경우
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

    def _filter_code_list_view(self, keyword, reset=True):
        # could be improved

        if reset:
            self.f_sv_code_df = pd.DataFrame(columns=('종목코드', '종목명'))
        for i, row in self.sv_code_df.iterrows():
            if keyword in row['종목코드'] + row['종목명']:
                self.f_sv_code_df = self.f_sv_code_df.append(row, ignore_index=True)

        if reset:
            self.f_db_code_df = pd.DataFrame(columns=('종목코드', '종목명', '갱신날짜'))
        for i, row in self.db_code_df.iterrows():
            if keyword in row['종목코드'] + row['종목명']:
                self.f_db_code_df = self.f_db_code_df.append(row, ignore_index=True)

        self.f_sv_view_model = PandasModel(self.f_sv_code_df)
        self.f_db_view_model = PandasModel(self.f_db_code_df)
        self.tableView.setModel(self.f_sv_view_model)
        self.tableView_2.setModel(self.f_db_view_model)

    # 종목 필터(검색)을 한 뒤 table view를 갱신하는 함수
    def filter_code_list_view(self):
        keyword = self.lineEdit_5.text()
        if len(keyword) == 0:
            self.tableView.setModel(self.sv_view_model)
            self.tableView_2.setModel(self.db_view_model)
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
        print(code_list)
        self._filter_code_list_view(code_list[0], reset=True)
        for code in code_list[1:]:
            self._filter_code_list_view(code, reset=False)
        print(code_list)

    @decorators.return_status_msg_setter
    def update_price_db(self, filtered=False):
        if filtered:
            fetch_code_df = self.f_sv_code_df
            db_code_df = self.f_db_code_df
        else:
            fetch_code_df = self.sv_code_df
            db_code_df = self.db_code_df

        if not is_market_open():
            latest_date = available_latest_date()
            print(latest_date)
            # 이미 DB 데이터가 최신인 종목들은 가져올 목록에서 제외한다
            already_up_to_date_codes = db_code_df.loc[db_code_df['갱신날짜']==latest_date]['종목코드'].values
            fetch_code_df = fetch_code_df.loc[fetch_code_df['종목코드'].apply(lambda x: x not in already_up_to_date_codes)]

        if self.radioButton.isChecked(): # 1분봉
            tick_unit = '분봉'
            count = 500000  # 서버 데이터 최대 reach 약 18.5만 이므로 (18/02/25 기준)
            tick_range = 1
        elif self.radioButton_3.isChecked(): # 5분봉
            tick_unit = '분봉'
            count = 100000
            tick_range = 5
        elif self.radioButton_2.isChecked(): # 일봉
            tick_unit = '일봉'
            count = 10000  # 10000개면 현재부터 1980년 까지의 데이터에 해당함. 충분.
            #count = 10
            tick_range = 1
        elif self.radioButton_4.isChecked(): # 주봉
            tick_unit = '주봉'
            count = 2000
        else: # 월봉
            tick_unit = '월봉'
            count = 500


        with sqlite3.connect(self.db_path) as con:
            cursor = con.cursor()
            tqdm_range = tqdm.trange(len(fetch_code_df), ncols=100)
            for i in tqdm_range:
                code = fetch_code_df.iloc[i]
                self.update_status_msg = '[{}] {}'.format(code[0], code[1])
                tqdm_range.set_description(preformat_cjk(self.update_status_msg, 25))

                from_date = 0
                if code[0] in self.db_code_df['종목코드'].tolist():
                    cursor.execute("SELECT date,close FROM {} ORDER BY date DESC LIMIT 1".format(code[0]))
                    last_elem = cursor.fetchall()
                    from_date = last_elem[0][0]
                    last_price = last_elem[0][1]

                if tick_unit == '일봉':  # 일봉 데이터 받기
                    if self.objStockChart.RequestDWM(code[0], ord('D'), count, self, from_date) == False:
                        continue
                elif tick_unit == '분봉':  # 분봉 데이터 받기
                    if self.objStockChart.RequestMT(code[0], ord('m'), tick_range, count, self, from_date) == False:
                        continue
                elif tick_unit == '주봉':  #주봉 데이터 받기
                    if self.objStockChart.RequestDWM(code[0], ord('W'), count, self, from_date) == False:
                        continue
                elif tick_unit == '월봉':  #주봉 데이터 받기
                    if self.objStockChart.RequestDWM(code[0], ord('M'), count, self, from_date) == False:
                        continue

                if tick_unit == '일봉':
                    df = pd.DataFrame(self.rcv_data, columns=['open', 'high', 'low', 'close', 'volume', 'value', 'num_listed','market_cap', 'foreign_rate', 'inst_netbuy'],
                                  index=self.rcv_data['date'])
                    if not (code[0] =='U001' or code[0] =='U201'):
                        df2 = pd.DataFrame(self.supply_data, columns=['person', 'foreign', 'inst_total', 'finance', 'insurance', 'toosin', 'bank',
                                                                  'gita_finance', 'pension', 'gita_inst', 'gita_foreign', 'samo',
                                                                  'nation'],
                                      index=self.supply_data['date'])
                        df = df.join(df2)
                else:
                    df = pd.DataFrame(self.rcv_data, columns=['open', 'high', 'low', 'close', 'volume'],
                                  index=self.rcv_data['date'])


                # 기존 DB와 겹치는 부분 제거
                if from_date != 0:
                    new_price = df.at[from_date,'close']
                    if new_price != last_price:
                        print('\n'+code[0],code[1],'수정주가 이벤트 발생')
                        df_old = pd.read_sql_query("SELECT * FROM "+code[0]+";", con).set_index('date')
                        df_old[['open','high','low','close']]=df_old[['open','high','low','close']]/last_price*new_price
                        df_old.to_sql(code[0], con, if_exists='replace', index_label='date')
                    df = df.loc[:from_date]
                    df = df.iloc[:-1]

                # 뒤집어서 저장 (결과적으로 date 기준 오름차순으로 저장됨)
                df = df.iloc[::-1]
                df.to_sql(code[0], con, if_exists='append', index_label='date')

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