g++ reciever_printer.cpp \
    -I/home/p/rpi-rgb-led-matrix/include \
    -L/home/p/rpi-rgb-led-matrix/lib \
    -lrgbmatrix -lpthread -lm -lprotobuf -lwebp -lcurl \
    -std=c++11 -O3 \
    -o simple_text_cpp