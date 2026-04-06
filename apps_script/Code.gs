/**
 * SPAO Buoy — Google Apps Script Webhook
 *
 * Receives RockBLOCK POST requests, decodes telemetry packets,
 * and appends decoded rows to per-IMEI worksheets.
 *
 * NOTE: This file is for reference only and is deployed separately
 * via Google Apps Script (not part of the Streamlit app).
 */

// ── Helpers ──────────────────────────────────────────────────────

function readUint16(bytes, offset) {
  return (bytes[offset] << 8) | bytes[offset + 1];
}

function readInt16(bytes, offset) {
  var val = readUint16(bytes, offset);
  return val >= 0x8000 ? val - 0x10000 : val;
}

function readInt32(bytes, offset) {
  var val = (bytes[offset] << 24) | (bytes[offset + 1] << 16) |
            (bytes[offset + 2] << 8) | bytes[offset + 3];
  return val;
}

function hexToBytes(hex) {
  var bytes = [];
  for (var i = 0; i < hex.length; i += 2) {
    bytes.push(parseInt(hex.substr(i, 2), 16));
  }
  return bytes;
}

function crc8(bytes, len) {
  var crc = 0;
  for (var i = 0; i < len; i++) {
    var extract = bytes[i];
    for (var j = 0; j < 8; j++) {
      var s = (crc ^ extract) & 0x01;
      crc >>= 1;
      if (s) crc ^= 0x8C;
      extract >>= 1;
    }
  }
  return crc;
}

// ── Decoders ─────────────────────────────────────────────────────

function decodeFY25(bytes) {
  // FY25: TENG current is stored as mA × 1000 (µA), divide to get mA
  var tengCurr = readUint16(bytes, 0) / 1000.0;

  // Previous session fields (bytes 2-14)
  var prev1stRB   = readUint16(bytes, 2) / 10.0;
  var prev2ndRB   = readUint16(bytes, 4) / 10.0;
  var prevGPS     = readUint16(bytes, 6) / 10.0;
  var prevTengCurr = readUint16(bytes, 8) / 1000.0;  // mA×1000 → mA
  var prevBattery  = readUint16(bytes, 10) / 1000.0; // mV → V
  var prevSuperCap = readUint16(bytes, 12) / 1000.0; // mV → V
  var prevEndMarker = bytes[14];

  // Current session
  var battery  = readUint16(bytes, 15) / 1000.0;
  var lat      = readInt32(bytes, 17)  / 1e7;
  var lon      = readInt32(bytes, 21)  / 1e7;
  var gpsTime  = readUint16(bytes, 25) * 100 / 1000;
  var pressure = readUint16(bytes, 27) / 1000.0;
  var intTemp  = readInt16(bytes, 29)  / 100.0;
  var humidity = readUint16(bytes, 31) / 10.0;
  var sst      = readInt16(bytes, 33)  / 1000.0;
  var superCap = readUint16(bytes, 35) / 1000.0;

  var crcByte = bytes[37];
  var crcCalc = crc8(bytes, 37);
  var crcOk   = (crcByte === crcCalc) || (crcByte === 0x00);

  return {
    version: "FY25", crcOk: crcOk,
    tengCurr: tengCurr,
    prev1stRB: prev1stRB, prev2ndRB: prev2ndRB, prevGPS: prevGPS,
    prevTengCurr: prevTengCurr, prevBattery: prevBattery,
    prevSuperCap: prevSuperCap, prevEndMarker: prevEndMarker,
    battery: battery, lat: lat, lon: lon, gpsTime: gpsTime,
    pressure: pressure, intTemp: intTemp,
    humidity: humidity, sst: sst, superCap: superCap
  };
}

function decodeFY26v3(bytes) {
  var tengCurr    = readUint16(bytes, 0);
  var prev1stRB   = readUint16(bytes, 2) / 10.0;
  var prev2ndRB   = readUint16(bytes, 4) / 10.0;
  var prevGPS     = readUint16(bytes, 6) / 10.0;
  var prevTengAvg = readUint16(bytes, 8);
  var prevTengMax = readUint16(bytes, 10);
  var prevBatt    = readUint16(bytes, 12) / 1000.0;
  var prevEnd     = readUint16(bytes, 14);
  var battery     = readUint16(bytes, 16) / 1000.0;
  var lat         = readInt32(bytes, 18)  / 1e7;
  var lon         = readInt32(bytes, 22)  / 1e7;
  var gpsTime     = readUint16(bytes, 26) / 10.0;
  var pressure    = readUint16(bytes, 28) / 1000.0;
  var intTemp     = readInt16(bytes, 30)  / 100.0;
  var humidity    = readUint16(bytes, 32) / 10.0;
  var sst         = readInt16(bytes, 34)  / 1000.0;

  var crcOk = (bytes[36] === crc8(bytes, 36));

  return {
    version: "FY26(v3)", crcOk: crcOk,
    tengCurr: tengCurr, prev1stRB: prev1stRB, prev2ndRB: prev2ndRB,
    prevGPS: prevGPS, prevTengAvg: prevTengAvg, prevTengMax: prevTengMax,
    prevBatt: prevBatt, prevEnd: prevEnd,
    battery: battery, lat: lat, lon: lon, gpsTime: gpsTime,
    pressure: pressure, intTemp: intTemp, humidity: humidity, sst: sst
  };
}

// ── Webhook Entry Point ──────────────────────────────────────────

function doPost(e) {
  try {
    var params = e.parameter;
    var imei   = params.imei || "unknown";
    var data   = params.data || "";

    var bytes  = hexToBytes(data);
    var len    = bytes.length;
    var result;

    if (len === 38 || len === 41) {
      result = decodeFY25(bytes);
    } else if (len === 37) {
      result = decodeFY26v3(bytes);
    } else {
      result = { version: "unknown", crcOk: false };
    }

    // Append to per-IMEI worksheet
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var ws;
    try {
      ws = ss.getSheetByName(imei);
    } catch (_) {
      ws = null;
    }
    if (!ws) {
      ws = ss.insertSheet(imei);
      ws.appendRow([
        "Receive Time", "Transmit Time", "IMEI", "MOMSN",
        "Raw Hex", "Packet Ver", "Bytes", "CRC Valid",
        "TENG Current Avg", "Battery", "GPS Latitude", "GPS Longitude",
        "GPS Acq Time", "Pressure", "Internal Temp", "Humidity", "SST"
      ]);
    }

    ws.appendRow([
      new Date().toISOString(),
      params.transmit_time || "",
      imei,
      params.momsn || "",
      data,
      result.version,
      len,
      result.crcOk,
      result.tengCurr || "",
      result.battery  || "",
      result.lat      || "",
      result.lon      || "",
      result.gpsTime  || "",
      result.pressure || "",
      result.intTemp  || "",
      result.humidity || "",
      result.sst      || ""
    ]);

    return ContentService.createTextOutput("OK");
  } catch (err) {
    // Log error to _errors tab
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var errSheet = ss.getSheetByName("_errors") || ss.insertSheet("_errors");
    errSheet.appendRow([new Date().toISOString(), err.toString()]);
    return ContentService.createTextOutput("ERROR: " + err);
  }
}
