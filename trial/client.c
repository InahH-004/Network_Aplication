#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>

#define PORT 8080
#define BUFFER_SIZE 4096

int main() {
    int sock;
    struct sockaddr_in server_addr;
    char buffer[BUFFER_SIZE];
    int pilihan;

    // Membuat socket
    sock = socket(AF_INET, SOCK_STREAM, 0);

    if (sock < 0) {
        perror("Socket gagal dibuat");
        return 1;
    }

    // Konfigurasi alamat server
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(PORT);
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    // Connect ke server
    if (connect(sock, (struct sockaddr *)&server_addr,
                sizeof(server_addr)) < 0) {
        perror("Gagal terhubung ke server");
        close(sock);
        return 1;
    }

    printf("Berhasil terhubung ke server.\n");

    while (1) {
        printf("\n===== MENU =====\n");
        printf("1. Jumlah karakter\n");
        printf("2. Jumlah kata\n");
        printf("3. Balik string\n");
        printf("4. Hapus huruf vokal\n");
        printf("5. Determinan dan invers matriks 3x3\n");
        printf("0. Keluar\n");
        printf("Pilih: ");

        scanf("%d", &pilihan);
        getchar(); // membersihkan newline

        // Kirim pilihan menu ke server
        sprintf(buffer, "%d", pilihan);

        send(sock, buffer, strlen(buffer), 0);

        if (pilihan == 0) {
            printf("Client keluar.\n");
            break;
        }

        // OPERASI STRING
        if (pilihan >= 1 && pilihan <= 4) {

            printf("Masukkan string: ");
            fgets(buffer, BUFFER_SIZE, stdin);

            // Hapus newline dari fgets
            buffer[strcspn(buffer, "\n")] = '\0';

            // Kirim string ke server
            send(sock, buffer, strlen(buffer), 0);

            // Terima hasil dari server
            memset(buffer, 0, BUFFER_SIZE);

            int bytes_received = recv(sock, buffer,
                                      BUFFER_SIZE - 1, 0);

            if (bytes_received > 0) {
                buffer[bytes_received] = '\0';

                printf("Hasil dari server: %s\n", buffer);
            }
        }

        // OPERASI MATRIKS
        else if (pilihan == 5) {

            printf("Masukkan matriks 3x3:\n");

            char matrix_data[BUFFER_SIZE] = "";

            for (int i = 0; i < 3; i++) {
                for (int j = 0; j < 3; j++) {

                    double nilai;

                    printf("M[%d][%d] = ", i, j);
                    scanf("%lf", &nilai);

                    char temp[50];

                    sprintf(temp, "%.2lf ", nilai);

                    strcat(matrix_data, temp);
                }
            }

            getchar();

            // Kirim matriks ke server
            send(sock, matrix_data,
                 strlen(matrix_data), 0);

            // Terima hasil
            memset(buffer, 0, BUFFER_SIZE);

            int bytes_received = recv(sock, buffer,
                                      BUFFER_SIZE - 1, 0);

            if (bytes_received > 0) {
                buffer[bytes_received] = '\0';

                printf("\nHasil dari server:\n%s\n", buffer);
            }
        }
    }

    close(sock);

    return 0;
}
