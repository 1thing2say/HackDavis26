#include <WiFiS3.h>

const char ssid[] = "ELEGOO-2CAF18A0ED30";

const char server[] = "192.168.4.1";
int port = 80;

// Match the baud rate your old working ESP32 code used
#define BAUD_RATE 921600

int status = WL_IDLE_STATUS;
WiFiClient client;

void setup() {
  Serial.begin(BAUD_RATE);

  // Wait for serial BUT with a timeout — on a Raspberry Pi,
  // while(!Serial) can hang forever because the Pi's USB-CDC
  // doesn't always trigger the DTR handshake that Serial checks for.
  unsigned long serialWait = millis();
  while (!Serial && (millis() - serialWait < 3000)) {
    ; // wait up to 3 seconds
  }

  delay(500);
  Serial.println("SYSTEM_BOOTING");

  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("ERROR: Communication with WiFi module failed!");
    while (true)
      ;
  }

  // Attempt to connect to ESP32 Camera Wi-Fi network.
  // Your old ESP32 code used WiFi.begin(ssid, "") and it works,
  // so the camera AP likely accepts WPA with empty passphrase.
  // We try that first, then fall back to open-network mode.
  int attempts = 0;
  while (status != WL_CONNECTED) {
    attempts++;
    Serial.print("CONNECTING_WIFI: Attempt ");
    Serial.println(attempts);

    if (attempts <= 3) {
      // Try with empty password first (matches your working ESP32 code)
      status = WiFi.begin(ssid, "");
    } else {
      // Fall back to open network mode
      status = WiFi.begin(ssid);
    }

    if (status != WL_CONNECTED) {
      delay(3000);
    }
  }

  Serial.print("WIFI_IP:");
  Serial.println(WiFi.localIP());
  Serial.println("SYSTEM_READY");
}

void loop() {
  // Listen for the 'S' character from the Python script to trigger capture
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'S' || cmd == 's') {
      fetchAndStreamImage();
    }
  }
}

void fetchAndStreamImage() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("PHOTO_SKIP:wifi_disconnected");
    return;
  }

  Serial.println("PHOTO_DEBUG:connecting_to_camera");

  if (!client.connect(server, port)) {
    Serial.println("PHOTO_SKIP:connection_failed");
    return;
  }

  Serial.println("PHOTO_DEBUG:requesting_image");

  client.println("GET /capture HTTP/1.0");
  client.print("Host: ");
  client.println(server);
  client.println("Connection: close");
  client.println();

  unsigned long timeout = millis();
  while (client.available() == 0) {
    if (millis() - timeout > 10000) {
      Serial.println("PHOTO_SKIP:timeout");
      client.stop();
      return;
    }
  }

  long imageLength = 0;
  bool isBody = false;

  // Parse HTTP headers
  while (client.connected() || client.available()) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
      line.trim();

      if (line.length() == 0) {
        isBody = true;
        break;
      }

      String lowerLine = line;
      lowerLine.toLowerCase();
      if (lowerLine.startsWith("content-length:")) {
        imageLength = line.substring(line.indexOf(':') + 1).toInt();
      }
    }
  }

  if (isBody && imageLength > 0) {
    Serial.print("PHOTO_DEBUG:image_size=");
    Serial.println(imageLength);

    // Flush any pending serial output before sending binary
    Serial.flush();
    delay(50);

    // Magic Header
    Serial.write(0xFF);
    Serial.write(0xAA);
    Serial.write(0xBB);
    Serial.write(0xCC);

    // 4-byte big-endian size
    Serial.write((imageLength >> 24) & 0xFF);
    Serial.write((imageLength >> 16) & 0xFF);
    Serial.write((imageLength >> 8) & 0xFF);
    Serial.write(imageLength & 0xFF);

    // Flush the header before streaming body
    Serial.flush();

    uint8_t buffer[256];
    long bytesRemaining = imageLength;

    while ((client.connected() || client.available()) && bytesRemaining > 0) {
      if (client.available()) {
        int bytesToRead = min(sizeof(buffer), (size_t)bytesRemaining);
        int bytesRead = client.read(buffer, bytesToRead);

        if (bytesRead > 0) {
          Serial.write(buffer, bytesRead);
          bytesRemaining -= bytesRead;
          // Let the USB-CDC buffer drain periodically
          if (bytesRemaining % 2048 < 256) {
            Serial.flush();
          }
        }
      }
    }

    // Ensure ALL bytes are flushed before sending the text completion marker
    Serial.flush();
    delay(50);

    Serial.println("PHOTO_DONE");
  } else {
    Serial.println("PHOTO_SKIP:no_content_length_found");
  }

  client.stop();
}