import requests
import time
import numpy as np
from datetime import datetime
import schedule
import folium
import webbrowser
import os
from folium import plugins
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

class AuroraSystem:
    def __init__(self, user_location, email_config=None):
        self.user_location = user_location
        self.kp_threshold = 4
        self.last_alert_time = None
        self.alert_cooldown = 3600  # seconds
        self.email_config = email_config

    def get_kp_index(self):
        try:
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1:
                    latest_entry = data[-1]
                    kp_value = float(latest_entry[1])
                    timestamp = latest_entry[0]
                    return kp_value, timestamp
            return None, None
        except Exception as e:
            print(f"Error fetching Kp index: {e}")
            return None, None

    def format_timestamp(self, timestamp_str):
        """Convert API timestamp to human-readable format"""
        if timestamp_str is None or timestamp_str == "Unknown":
            return "Unknown"
        
        try:
            # Parse the timestamp from API (format: "2024-01-15 12:00:00")
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%Y-%m-%d %I:%M %p UTC")
        except Exception as e:
            print(f"Error formatting timestamp: {e}")
            return timestamp_str  # Return original if fail to parse

    def calculate_aurora_visibility(self, kp_index):
        visibility_map = {
            9: 35, 8: 40, 7: 45, 6: 50, 5: 55, 4: 60, 3: 65, 2: 70, 1: 75, 0: 80
        }
        user_lat = self.user_location['lat']
        visible_latitude = 80
        for kp_level in sorted(visibility_map.keys(), reverse=True):
            if kp_index >= kp_level:
                visible_latitude = visibility_map[kp_level]
                break
        is_visible = user_lat >= visible_latitude
        status = f"Kp={kp_index:.1f}, Visible south to {visible_latitude}°N"
        return is_visible, status, visible_latitude

    def create_aurora_map(self):
        kp_index, timestamp = self.get_kp_index()
        if kp_index is None:
            kp_index = 0
            timestamp = "Unknown"

        formatted_timestamp = self.format_timestamp(timestamp)
        
        #local time for map generation
        current_time = datetime.now().strftime("%Y-%m-%d %I:%M %p CST")

        is_visible, visibility_info, visible_latitude = self.calculate_aurora_visibility(kp_index)

        #centered on North America
        m = folium.Map(
            location=[55, -100],  #North America
            zoom_start=4,
            tiles='OpenStreetMap'
        )

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satellite',
            overlay=False,
            control=True
        ).add_to(m)

        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='National Geographic',
            overlay=False,
            control=True
        ).add_to(m)

        aurora_points = []
        for lon in range(-180, 181, 5):
            aurora_points.append([visible_latitude, lon])
        
        #aurora visibility line
        folium.PolyLine(
            locations=aurora_points,
            color='green',
            weight=4,
            opacity=0.8,
            popup=f"Aurora Visibility Line (Kp={kp_index:.1f})"
        ).add_to(m)

        #aurora visibility zone (area where aurora might be visible)
        aurora_zone = []
        for lon in range(-180, 181, 10):
            aurora_zone.append([visible_latitude, lon])
        for lon in range(180, -181, -10):
             #North boundary
            aurora_zone.append([90, lon])

        folium.Polygon(
            locations=aurora_zone,
            color='green',
            weight=2,
            fill=True,
            fillColor='green',
            fillOpacity=0.2,
            popup=f"Potential Aurora Zone (Kp={kp_index:.1f})"
        ).add_to(m)

        #latitude reference lines
        for lat in [30, 40, 50, 60, 70]:
            lat_line = [[lat, -180], [lat, 180]]
            folium.PolyLine(
                locations=lat_line,
                color='gray',
                weight=1,
                opacity=0.5,
                dashArray='5, 5'
            ).add_to(m)
            
            # latitude labels
            folium.Marker(
                location=[lat, -60],
                icon=folium.DivIcon(
                    html=f'<div style="font-size: 12px; color: gray;">{lat}°N</div>',
                    icon_size=(40, 20),
                    icon_anchor=(20, 10)
                )
            ).add_to(m)

        #user location
        user_color = 'red' if not is_visible else 'orange'
        user_icon = 'home'
        
        folium.Marker(
            location=[self.user_location['lat'], self.user_location['lon']],
            popup=f"""
            <b>Your Location</b><br>
            Lat: {self.user_location['lat']:.2f}°N<br>
            Lon: {self.user_location['lon']:.2f}°W<br>
            Aurora Visible: {'Yes' if is_visible else 'No'}<br>
            Kp Index: {kp_index:.1f}<br>
            Distance to Aurora: {abs(self.user_location['lat'] - visible_latitude):.1f}° south
            """,
            tooltip="Your Location",
            icon=folium.Icon(color=user_color, icon=user_icon)
        ).add_to(m)

        legend_html = f'''
        <div style="position: fixed; 
                    bottom: 50px; right: 50px; width: 280px; height: 210px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.3);">
        <h4 style="margin-top: 0; color: #333;">Aurora Forecast</h4>
        <p><b>Kp Index:</b> {kp_index:.1f}</p>
        <p><b>Data From:</b> {formatted_timestamp}</p>
        <p><b>Map Generated:</b> {current_time}</p>
        <p><b>Visible South To:</b> {visible_latitude}°N</p>
        <p><b>Your Location:</b> {'Visible' if is_visible else 'Not Visible'}</p>
        <hr style="margin: 10px 0;">
        <p style="margin: 5px 0;"><span style="color:green;">●</span> Aurora Visibility Zone</p>
        <p style="margin: 5px 0;"><span style="color:red;">🏠</span> Your Location</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        folium.LayerControl().add_to(m)

        # Saving data with timestamp in filename
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        map_file = f'aurora_forecast_{timestamp_str}.html'
        m.save(map_file)
        
        #for opening in browser
        webbrowser.open('file://' + os.path.realpath(map_file))
        
        print(f"Map saved as: {map_file}")
        print(f"Data timestamp: {formatted_timestamp}")
        print(f"Map generated: {current_time}")
        print("Map opened in your default web browser")
        
        return map_file

    def send_daily_report_email(self):
        """Send daily aurora report email at noon"""
        if not self.email_config:
            print("Email not configured - skipping daily report")
            return False
            
        print("SENDING DAILY AURORA REPORT...")
        
        # Get current aurora data
        kp_index, timestamp = self.get_kp_index()
        if kp_index is None:
            kp_index = 0
            timestamp = "Unknown"
            
        formatted_timestamp = self.format_timestamp(timestamp)
        is_visible, visibility_info, visible_latitude = self.calculate_aurora_visibility(kp_index)
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = f"Daily Aurora Report - Kp={kp_index:.1f}"
            
            # Generate current map
            print("Generating current aurora map...")
            map_file = self.create_aurora_map()
            
            current_time = datetime.now().strftime('%Y-%m-%d %I:%M %p CST')
            
            # Email body
            body = f"""
DAILY AURORA REPORT 🌌

Your daily aurora conditions update for East Peoria, Illinois:

Current Conditions (as of {current_time}):
- Kp Index: {kp_index:.1f}
- {visibility_info}
- Your Location: {self.user_location['lat']:.2f}°N, {self.user_location['lon']:.2f}°W
- Data From: {formatted_timestamp}

Aurora Status for Your Location:
- {'VISIBLE - Aurora may be visible tonight!' if is_visible else 'NOT VISIBLE - Aurora not expected to be visible'}

{'AURORA HUNTING TONIGHT:' if is_visible else 'MONITORING STATUS:'}
- {'''1. Check the attached map for current conditions.
- 2. Look for dark skies away from city lights.
- 3. Best viewing time: 10 PM - 2 AM.
- 4. Look north for green glow or dancing lights.
- 5. Be patient - aurora can appear and disappear quickly.''' if is_visible else '''1. Check attached map for current conditions.
- 2. Aurora threshold for your location: Kp ≥ 4.
- 3. You'll receive alerts when conditions improve.
- 4. Keep monitoring for geomagnetic storms.'''}

Weather Reminder:
- Check local weather for clear skies.
- Aurora is best viewed on dark, clear nights.
- Light pollution reduces visibility.

The attached map shows the current aurora forecast and your location.

{'Happy aurora hunting tonight!' if is_visible else 'Keep watching the skies!'}

---
Daily Aurora Report from your Aurora Monitoring System
Next report: Tomorrow at 12:00 PM CST
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach the map file
            if os.path.exists(map_file):
                print(f"📎 Attaching map file: {map_file}")
                with open(map_file, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {os.path.basename(map_file)}'
                    )
                    msg.attach(part)
            
            # Send email
            print("Connecting to SMTP server...")
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            print("Logging in...")
            server.login(self.email_config['from_email'], self.email_config['password'])
            print("Sending daily report...")
            text = msg.as_string()
            server.sendmail(self.email_config['from_email'], self.email_config['to_email'], text)
            server.quit()
            
            print("DAILY AURORA REPORT SENT SUCCESSFULLY!")
            print(f"   Sent to: {self.email_config['to_email']}")
            print(f"   Subject: Daily Aurora Report - Kp={kp_index:.1f}")
            print(f"   Time: {current_time}")
            print(f"   Aurora Status: {'VISIBLE' if is_visible else 'NOT VISIBLE'}")
            
            return True
            
        except Exception as e:
            print(f"FAILED TO SEND DAILY REPORT EMAIL: {e}")
            return False

    def send_startup_email(self):
        """Send startup confirmation email when system starts"""
        if not self.email_config:
            print("Email not configured - skipping startup email")
            return False
            
        print("SENDING STARTUP CONFIRMATION EMAIL...")
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = "Aurora Monitoring System Started"
            
            startup_time = datetime.now().strftime('%Y-%m-%d %I:%M %p CST')
            
            # Email body
            body = f"""
AURORA MONITORING SYSTEM STARTED

The Aurora Monitoring System is now active and watching the skies!

System Details:
- Started: {startup_time}
- Monitoring Location: East Peoria, Illinois
- Coordinates: {self.user_location['lat']:.2f}°N, {self.user_location['lon']:.2f}°W
- Alert Threshold: Kp ≥ {self.kp_threshold}
- Email Alerts: ENABLED

What happens next:
- System checks aurora conditions every 30 minutes.
- Daily reports sent at 12:00 PM CST.

Aurora Alert Conditions:
- Kp Index must be ≥ {self.kp_threshold}.
- Aurora must be visible from your latitude ({self.user_location['lat']:.1f}°N).
- Cooldown period: 1 hour between alerts.

System Status: 🟢 ACTIVE AND MONITORING

This email confirms your Aurora Monitoring System is working correctly and ready to alert you when the northern lights are visible!


---
Aurora Monitoring System Startup Confirmation
System will continue monitoring until stopped.
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            print("Connecting to SMTP server...")
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            print("Logging in...")
            server.login(self.email_config['from_email'], self.email_config['password'])
            print("Sending startup confirmation...")
            text = msg.as_string()
            server.sendmail(self.email_config['from_email'], self.email_config['to_email'], text)
            server.quit()
            
            print("STARTUP CONFIRMATION EMAIL SENT SUCCESSFULLY!")
            print(f"   Sent to: {self.email_config['to_email']}")
            print(f"   Subject: Aurora Monitoring System Started")
            print(f"   Time: {startup_time}")
            
            return True
            
        except Exception as e:
            print(f"FAILED TO SEND STARTUP EMAIL: {e}")
            return False

    def send_email_alert(self, kp_index, visibility_info, map_file):
        """Send email alert with aurora information and map attachment"""
        if not self.email_config:
            print("Email not configured - skipping email alert")
            return False
            
        print("SENDING AURORA ALERT EMAIL...")
        print(f"   Kp Index: {kp_index:.1f}")
        print(f"   Visibility: {visibility_info}")
        print(f"   From: {self.email_config['from_email']}")
        print(f"   To: {self.email_config['to_email']}")
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = f"Aurora Alert! Kp={kp_index:.1f} - Visible from your location!"
            
            alert_time = datetime.now().strftime('%Y-%m-%d %I:%M %p CST')
            
            body = f"""
AURORA ALERT! 🌌

Great news! Aurora may be visible from your location tonight!

Current Conditions:
- Kp Index: {kp_index:.1f}
- {visibility_info}
- Your Location: {self.user_location['lat']:.2f}°N, {self.user_location['lon']:.2f}°W
- Alert Time: {alert_time}

What to do:
- 1. Check the attached map to see the aurora forecast.
- 2. Find a dark location away from city lights.
- 3. Look north after sunset.
- 4. Aurora is most active between 10 PM and 2 AM.
- 5. Be patient - aurora can appear and disappear quickly.

Tips for viewing:
- Give your eyes 20-30 minutes to adjust to darkness.
- Use a red flashlight to preserve night vision.
- Aurora may appear as a green glow or dancing lights.
- Check weather for clear skies.

The attached map shows current conditions and your location.

Happy aurora hunting!

---
This alert was generated by your Aurora Monitoring System.
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach the map file
            if os.path.exists(map_file):
                print(f"Attaching map file: {map_file}")
                with open(map_file, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {os.path.basename(map_file)}'
                    )
                    msg.attach(part)
            
            # Send email
            print("Connecting to SMTP server...")
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            print("Logging in...")
            server.login(self.email_config['from_email'], self.email_config['password'])
            print("Sending aurora alert...")
            text = msg.as_string()
            server.sendmail(self.email_config['from_email'], self.email_config['to_email'], text)
            server.quit()
            
            print("AURORA ALERT EMAIL SENT SUCCESSFULLY!")
            print(f"   Sent to: {self.email_config['to_email']}")
            print(f"   Subject: Aurora Alert! Kp={kp_index:.1f}")
            print(f"   Time: {alert_time}")
            
            return True
            
        except Exception as e:
            print(f"FAILED TO SEND AURORA ALERT EMAIL: {e}")
            return False

    def notify_aurora_console(self, kp_index, visibility_info):
        current_time = datetime.now().strftime('%Y-%m-%d %I:%M %p CST')
        print(f"\nAurora Alert! Kp={kp_index:.1f}")
        print(f"Visibility info: {visibility_info}")
        print(f"Your Location: {self.user_location['lat']:.2f}°N, {self.user_location['lon']:.2f}°W")
        print(f"Generated at: {current_time}\n")

    def check_aurora_conditions(self):
        current_time = datetime.now().strftime('%Y-%m-%d %I:%M %p CST')
        print(f"Checking aurora conditions at {current_time}")
        
        kp_index, timestamp = self.get_kp_index()
        if kp_index is None:
            print("Unable to fetch Kp index")
            return
        
        formatted_timestamp = self.format_timestamp(timestamp)
        print(f"Current Kp index: {kp_index} (data from {formatted_timestamp})")
        
        is_visible, visibility_info, _ = self.calculate_aurora_visibility(kp_index)
        
        should_alert = (
            kp_index >= self.kp_threshold and
            is_visible and
            (self.last_alert_time is None or time.time() - self.last_alert_time > self.alert_cooldown)
        )
        
        if should_alert:
            self.notify_aurora_console(kp_index, visibility_info)
            self.last_alert_time = time.time()
            
            print("Generating interactive map...")
            map_file = self.create_aurora_map()
            
            if self.email_config:
                self.send_email_alert(kp_index, visibility_info, map_file)
        else:
            print(f"No alert needed. Visible: {is_visible}, Kp: {kp_index}")
            # Still generate map for monitoring
            print("Generating interactive map...")
            self.create_aurora_map()

    def run_monitoring(self):
        print("STARTING AURORA MONITORING SYSTEM...")
        
        if self.email_config:
            self.send_startup_email()
        
        print("Scheduling daily reports for 12:00 PM CST...")
        print("Scheduling aurora condition checks every 30 minutes...")
        print("Interactive maps will open in your web browser.")
        
        schedule.every().day.at("12:00").do(self.send_daily_report_email)
        
        # Schedule aurora condition checks every 30 minutes
        schedule.every(30).minutes.do(self.check_aurora_conditions)
        
        # Run aurora check once immediately
        self.check_aurora_conditions()
        
        print("AURORA MONITORING SYSTEM IS NOW ACTIVE!")
        print("   Startup email sent")
        print("   Daily reports scheduled for 12:00 PM CST")
        print("   Aurora alerts enabled when Kp ≥ 4")
        print("   Interactive maps will open automatically")
        print("\nPress Ctrl+C to stop monitoring...")
        
        while True:
            schedule.run_pending()
            time.sleep(60)

    def run_once(self):
        """Run the aurora check just once (useful for testing)"""
        print("STARTING AURORA SYSTEM (SINGLE RUN)...")
        
        # Send startup email first
        if self.email_config:
            self.send_startup_email()
        
        print("Running single aurora check...")
        self.check_aurora_conditions()
    
    def test_email_only(self):
        """Test email configuration without checking aurora conditions"""
        print("TESTING EMAIL CONFIGURATION ONLY...")
        return self.send_startup_email()

if __name__ == "__main__":
    # East Peoria, Illinois coordinates
    user_location = {
        'lat': 40.6664,
        'lon': -89.5890
    }
    
    # Email configuration - FILL IN YOUR ACTUAL EMAIL DETAILS:
    email_config = {
        'from_email': 'adamkul0126@gmail.com',   # ← Replace with your Gmail address
        'password': 'vllhguaooklsipue',         # ← Replace with your Gmail app password
        'to_email': 'adamkul0126@gmail.com',     # ← Email address to receive alerts
        'smtp_server': 'smtp.gmail.com',         # ← Keep this for Gmail
        'smtp_port': 587                         # ← Keep this for Gmail
    }
    
    # To disable email alerts, uncomment the line below:
    # email_config = None
     
    aurora_system = AuroraSystem(user_location, email_config)
    
    # Choose which setting to run:
    
    # 1. CONTINUOUS MONITORING - sends startup email + daily reports at noon CST
    #aurora_system.run_monitoring()
    
    # 2. SINGLE RUN (testing) - sends startup email then runs once
    # aurora_system.run_once()
    
    # 3. EMAIL TEST ONLY - just tests email configuration
    aurora_system.test_email_only()