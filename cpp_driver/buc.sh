gcc matrix_influx_c.c \
    -o matrix_influx_c_app \
    -I/usr/local/include -I/usr/include \
    -L/usr/local/lib -L/usr/lib \
    -lrgbmatrix -lcurl -lcjson -lpthread -lm \
    -O2 # Optional optimization flag