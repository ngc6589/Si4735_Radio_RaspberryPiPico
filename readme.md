# Si4735ラジオ概要

![Image 1](Materials/Si4735Radio-1.jpg)
![Image 2](Materials/Si4735Radio-2.jpg)
![Image 3](Materials/Si4735Radio-3.jpg)


Raspberry Pi Pico と ILI9341 タッチ液晶を使用し、Si4735 DSP ラジオチップを動かすラジオを製作しました。写真のように周波数を入力してチューニングする画面、ステップ周波数のUP/DOWNチューニング、選局リストからチューニングのモードを備えています。
このラジオの Raspberry Pi Pico のファームウエアは micropython に lvgl グラフィックライブラリをバインドした lv_micropython というものを使用しています。この lv_micropython は https://github.com/lvgl/lv_micropython にて公開されています。これにフリーフォントなどを加えたカスタマイズ版のファームウエアを作成しています。
このファームウエアに micropython で記述したラジオアプリケーションを動かして上記機能を実現しました。

問題

* Raspberry Pi Pico の RAMが 264kB なので画面にグラフィックスウイジェットをたくさん出すとハングアップします。特に選局リストは放送局分のオブジェクトを内部で作成するので、選局リストをいじくりまわしていると固まることが多いです。選局して放置している分には特にハングアップは発生しません。

これはヒープ領域不足で発生し、その原因は画面のウイジェット数や変数領域などに依存するので、今後 lvgl や micropython の新バージョンがリリースされても改善の見込みはありません。

