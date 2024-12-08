# Felt Temperature (UTCI Approximation)

## English

This project uses a simplified calculation to approximate the Universal Thermal Climate Index (UTCI). The UTCI is a comprehensive measure of how outdoor conditions "feel" to humans, normally taking into account factors like:

- Air temperature (Ta)
- Mean radiant temperature (Tmrt)
- Wind speed (Va)
- Humidity (via vapor pressure, e)

A full UTCI calculation involves a highly complex equation with over 100 terms and requires accurate Tmrt data for realistic results. In this implementation, we simplify the approach:

1. **Tmrt ≈ Ta**  
   We assume the mean radiant temperature (Tmrt) equals the air temperature (Ta). In reality, Tmrt is affected by solar radiation, surrounding surfaces, and other radiative factors.

2. **Simple Vapor Pressure Calculation**  
   The vapor pressure e is derived from temperature and relative humidity (RH):

3. **Highly Simplified UTCI Approximation**  
Instead of the full polynomial equation, we use a simpler formula that resembles an "apparent temperature" approach:


**Note:** This is **not** an official or accurate UTCI formula. It is merely an approximation to demonstrate how to integrate a more complex index calculation into Home Assistant. For truly accurate UTCI values, proper Tmrt data and the full official calculation are required.

**Summary:**  
The sensor provides a value that approximates UTCI but is not a fully accurate representation. For proper UTCI usage, you need correct Tmrt and the complete polynomial calculation method.

