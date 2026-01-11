from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Link(Base):
    __tablename__ = 'inventory'

    id = Column(Integer, primary_key=True)
    link_id_str = Column(String(50), unique=True, nullable=False)
    
    # Basic Info
    link_name = Column(String(255))
    pop_name = Column(String(100))
    location = Column(String(100))
    
    # Network
    client_ip = Column(String(50))
    base_ip = Column(String(50))
    gateway_ip = Column(String(50))
    
    # Radio / Tech Details
    model = Column(String(100))
    vendor = Column(String(50))
    serial = Column(String(100), default='N/A')
    
    # Fields that were causing the error:
    connection_type = Column(String(50))  # <--- Added this
    device_mode = Column(String(50))      # <--- Added this
    channel_width = Column(String(50))    # <--- Added this (was channel in excel)
    frequency_used = Column(String(50))
    frequency_type = Column(String(50))
    link_type = Column(String(50))
    ssid = Column(String(100))
    
    # Live Status Fields
    eth_speed = Column(String(20), default='Unknown')
    eth_duplex = Column(String(20), default='Unknown')
    
    # Config
    snmp_community = Column(String(50), default='public')
    is_active = Column(Boolean, default=True)

class MonitoringLog(Base):
    __tablename__ = 'monitoring_logs'

    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    status = Column(String(20))
    latency = Column(Float)
    loss = Column(Float)
    rssi = Column(Float)

# Connect to DB
engine = create_engine('sqlite:///amberit_noc.db') 

def init_db():
    Base.metadata.create_all(engine)