#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static const char *socket_path = "/tmp/hv_jpx_merged_socket";

#define BUF_SIZE 4096

static int write_all(int fd, const char *buf, size_t length) {
    while (length > 0) {
        ssize_t written = write(fd, buf, length);

        if (written < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        if (written == 0) {
            errno = EIO;
            return -1;
        }
        buf += written;
        length -= (size_t) written;
    }
    return 0;
}

int main(int argc, char **argv) {
    struct sockaddr_un addr;
    char buf[BUF_SIZE];
    const char *argument_file = NULL;
    FILE *response;
    int fd, input_fd = STDIN_FILENO;
    ssize_t count;
    int i;

    if (signal(SIGPIPE, SIG_IGN) == SIG_ERR) {
        perror("signal error");
        return EXIT_FAILURE;
    }

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-s") == 0 && i + 1 < argc) {
            argument_file = argv[++i];
        } else if (strcmp(argv[i], "--socket") == 0 && i + 1 < argc) {
            socket_path = argv[++i];
        } else {
            fprintf(stderr, "usage: hv_jpx_mergec [-s argfile] [--socket path]\n");
            return EXIT_FAILURE;
        }
    }

    if (argument_file != NULL && strcmp(argument_file, "/dev/stdin") != 0) {
        input_fd = open(argument_file, O_RDONLY);
        if (input_fd == -1) {
            perror(argument_file);
            return EXIT_FAILURE;
        }
    }

    if ((fd = socket(AF_UNIX, SOCK_STREAM, 0)) == -1) {
        perror("socket error");
        return EXIT_FAILURE;
    }

    memset(&addr, 0, sizeof addr);
    addr.sun_family = AF_UNIX;
    if (strlen(socket_path) >= sizeof addr.sun_path) {
        fprintf(stderr, "socket path is too long: %s\n", socket_path);
        return EXIT_FAILURE;
    }
    strncpy(addr.sun_path, socket_path, sizeof addr.sun_path - 1);

    if (connect(fd, (struct sockaddr *) &addr, sizeof addr) == -1) {
        perror("connect error");
        return EXIT_FAILURE;
    }

    while ((count = read(input_fd, buf, sizeof buf)) != 0) {
        if (count < 0) {
            if (errno == EINTR)
                continue;
            perror("read error");
            return EXIT_FAILURE;
        }
        if (write_all(fd, buf, (size_t) count) == -1) {
            perror("write error");
            return EXIT_FAILURE;
        }
    }
    if (input_fd != STDIN_FILENO)
        close(input_fd);

    if (shutdown(fd, SHUT_WR) == -1) {
        perror("shutdown error");
        return EXIT_FAILURE;
    }

    response = fdopen(fd, "r");
    if (response == NULL) {
        perror("fdopen error");
        return EXIT_FAILURE;
    }
    if (fgets(buf, sizeof buf, response) == NULL) {
        fprintf(stderr, "merge daemon closed the connection without a response\n");
        return EXIT_FAILURE;
    }
    if (strcmp(buf, "OK\n") != 0) {
        fputs(buf, stderr);
        fclose(response);
        return EXIT_FAILURE;
    }
    fclose(response);

    return EXIT_SUCCESS;
}
