#include <math.h>

double connector_power(double base, double exponent) {
    return pow(base, exponent);
}

double connector_square_root(double value) {
    return sqrt(value);
}

double connector_safe_ratio(double numerator, double denominator, double default_value) {
    if (denominator == 0.0) {
        return default_value;
    }
    return numerator / denominator;
}
