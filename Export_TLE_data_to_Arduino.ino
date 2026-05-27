#include <ArduinoJson.h>
#include <AccelStepper.h>
#include <LiquidCrystal.h>

// Define stepper motor connections
#define STEPPER_1_PIN1 2
#define STEPPER_1_PIN2 3
#define STEPPER_2_PIN1 4
#define STEPPER_2_PIN2 5

// Define the steps per revolution for the stepper motors
const int STEPS_PER_REV = 200;

// Create instances of the stepper motors
AccelStepper stepper1(AccelStepper::FULL4WIRE, STEPPER_1_PIN1, STEPPER_1_PIN2);
AccelStepper stepper2(AccelStepper::FULL4WIRE, STEPPER_2_PIN1, STEPPER_2_PIN2);

// Create an instance of the LiquidCrystal library
LiquidCrystal lcd(12, 11, 7, 6, 5, 4);

// Function to move stepper motors by one degree
void moveStepperMotor(AccelStepper& stepper) {
  stepper.move(1);
  stepper.runToPosition();
}

void setup() {
  // Set up the LCD screen
  lcd.begin(16, 2);
  lcd.print("Ready");

  // Set the maximum speed and acceleration for the stepper motors
  stepper1.setMaxSpeed(1000);
  stepper1.setAcceleration(1000);
  stepper2.setMaxSpeed(1000);
  stepper2.setAcceleration(1000);

  Serial.begin(9600); // Start serial communication
}

void loop() {
  if (Serial.available()) {
    // Read the incoming JSON data
    StaticJsonDocument<256> jsonBuffer;
    DeserializationError error = deserializeJson(jsonBuffer, Serial);

    if (error) {
      lcd.clear();
      lcd.print("JSON Error");
      delay(2000);
      lcd.clear();
      lcd.print("Ready");
      return;
    }

    // Retrieve position and speed data from the JSON object
    float radius = jsonBuffer["radius"];
    float inclination = jsonBuffer["inclination"];
    float azimuth = jsonBuffer["azimuth"];
    float speed = jsonBuffer["speed"];
    float argument_periapsis = jsonBuffer["argument_periapsis"];
    float eccentricity = jsonBuffer["eccentricity"];
    float mean_anomaly = jsonBuffer["mean_anomaly"];
    float semi_major_axis = jsonBuffer["semi_major_axis"];
    float longitude = jsonBuffer["longitude"];

    // Convert Kepler coordinates to Cartesian coordinates
    float x, y, z;

    // Calculate the true anomaly from the mean anomaly and eccentricity
    float true_anomaly = mean_anomaly + (2 * eccentricity - 0.25 * pow(eccentricity, 3)) * sin(mean_anomaly);

    // Calculate the distance from the focus (radius) using the semi-major axis and eccentricity
    radius = semi_major_axis * (1 - pow(eccentricity, 2)) / (1 + eccentricity * cos(true_anomaly));

    // Calculate the Cartesian coordinates from the Kepler elements
    x = radius * (cos(argument_periapsis) * cos(true_anomaly + longitude) - sin(argument_periapsis) * sin(true_anomaly + longitude) * cos(inclination));
    y = radius * (sin(argument_periapsis) * cos(true_anomaly + longitude) + cos(argument_periapsis) * sin(true_anomaly + longitude) * cos(inclination));
    z = radius * (sin(inclination) * sin(true_anomaly + longitude));

    lcd.clear();
    lcd.print("Data Received");
    delay(2000);
    lcd.clear();
    lcd.print("Cartesian:");
    lcd.setCursor(0, 1);
    lcd.print(x);
    lcd.print(",");
    lcd.print(y);
    lcd.print(",");
    lcd.print(z);

    // Set speed and move stepper motors to the desired position
    stepper1.setSpeed(speed);
    stepper1.moveTo(x * STEPS_PER_REV);
    stepper1.runToPosition();

    stepper2.setSpeed(speed);
    stepper2.moveTo(y * STEPS_PER_REV);
    stepper2.runToPosition();
  }
}
