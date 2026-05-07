// OPC UA Reader — Eclipse Milo 0.6.12 + NiFi groovyx
// Additional classpath: /opt/nifi/nifi-current/data/milo-jars/*.jar
// Scheduling: Timer driven, 2 sec

import org.eclipse.milo.opcua.sdk.client.OpcUaClient
import org.eclipse.milo.opcua.sdk.client.api.config.OpcUaClientConfig
import org.eclipse.milo.opcua.sdk.client.api.config.OpcUaClientConfigBuilder
import org.eclipse.milo.opcua.stack.core.security.SecurityPolicy
import org.eclipse.milo.opcua.stack.core.types.builtin.NodeId
import org.eclipse.milo.opcua.stack.core.types.builtin.LocalizedText
import org.eclipse.milo.opcua.stack.core.types.enumerated.TimestampsToReturn
import org.apache.nifi.processor.io.OutputStreamCallback
import groovy.json.JsonOutput

@groovy.transform.Field static final String OPC_ENDPOINT = "opc.tcp://10.85.3.100:53530/OPCUA/SimulationServer"
@groovy.transform.Field static final String SOURCE_ID = "mintserver-prosys"
@groovy.transform.Field static final String DEVICE_ID = "opc-prosys-300tags"

// Deferred: store as [name, ns, id] — NodeId objects created at first run only
@groovy.transform.Field
static final List NODE_DEFS = [
    ["Counter", 3, 1001],
    ["Random", 3, 1002],
    ["Sawtooth", 3, 1003],
    ["Sinusoid", 3, 1004],
    ["Square", 3, 1005],
    ["Triangle", 3, 1006],
    ["Constant", 3, 1007],
    ["Temp_Boiler_01", 3, 2001],
    ["Temp_Boiler_02", 3, 2002],
    ["Temp_Boiler_03", 3, 2003],
    ["Temp_Boiler_04", 3, 2004],
    ["Temp_Boiler_05", 3, 2005],
    ["Temp_Boiler_06", 3, 2006],
    ["Temp_Boiler_07", 3, 2007],
    ["Temp_Boiler_08", 3, 2008],
    ["Temp_Boiler_09", 3, 2009],
    ["Temp_Boiler_10", 3, 2010],
    ["Temp_Boiler_11", 3, 2011],
    ["Temp_Boiler_12", 3, 2012],
    ["Temp_Boiler_13", 3, 2013],
    ["Temp_Boiler_14", 3, 2014],
    ["Temp_Boiler_15", 3, 2015],
    ["Temp_Boiler_16", 3, 2016],
    ["Temp_Boiler_17", 3, 2017],
    ["Temp_Boiler_18", 3, 2018],
    ["Temp_Boiler_19", 3, 2019],
    ["Temp_Boiler_20", 3, 2020],
    ["Temp_HeatEx_01", 3, 2021],
    ["Temp_HeatEx_02", 3, 2022],
    ["Temp_HeatEx_03", 3, 2023],
    ["Temp_HeatEx_04", 3, 2024],
    ["Temp_HeatEx_05", 3, 2025],
    ["Temp_HeatEx_06", 3, 2026],
    ["Temp_HeatEx_07", 3, 2027],
    ["Temp_HeatEx_08", 3, 2028],
    ["Temp_HeatEx_09", 3, 2029],
    ["Temp_HeatEx_10", 3, 2030],
    ["Press_Line_01", 3, 2031],
    ["Press_Line_02", 3, 2032],
    ["Press_Line_03", 3, 2033],
    ["Press_Line_04", 3, 2034],
    ["Press_Line_05", 3, 2035],
    ["Press_Line_06", 3, 2036],
    ["Press_Line_07", 3, 2037],
    ["Press_Line_08", 3, 2038],
    ["Press_Line_09", 3, 2039],
    ["Press_Line_10", 3, 2040],
    ["Press_Line_11", 3, 2041],
    ["Press_Line_12", 3, 2042],
    ["Press_Line_13", 3, 2043],
    ["Press_Line_14", 3, 2044],
    ["Press_Line_15", 3, 2045],
    ["Press_Line_16", 3, 2046],
    ["Press_Line_17", 3, 2047],
    ["Press_Line_18", 3, 2048],
    ["Press_Line_19", 3, 2049],
    ["Press_Line_20", 3, 2050],
    ["Press_Tank_01", 3, 2051],
    ["Press_Tank_02", 3, 2052],
    ["Press_Tank_03", 3, 2053],
    ["Press_Tank_04", 3, 2054],
    ["Press_Tank_05", 3, 2055],
    ["Press_Tank_06", 3, 2056],
    ["Press_Tank_07", 3, 2057],
    ["Press_Tank_08", 3, 2058],
    ["Press_Tank_09", 3, 2059],
    ["Press_Tank_10", 3, 2060],
    ["Flow_Main_01", 3, 2061],
    ["Flow_Main_02", 3, 2062],
    ["Flow_Main_03", 3, 2063],
    ["Flow_Main_04", 3, 2064],
    ["Flow_Main_05", 3, 2065],
    ["Flow_Main_06", 3, 2066],
    ["Flow_Main_07", 3, 2067],
    ["Flow_Main_08", 3, 2068],
    ["Flow_Main_09", 3, 2069],
    ["Flow_Main_10", 3, 2070],
    ["Flow_Main_11", 3, 2071],
    ["Flow_Main_12", 3, 2072],
    ["Flow_Main_13", 3, 2073],
    ["Flow_Main_14", 3, 2074],
    ["Flow_Main_15", 3, 2075],
    ["Flow_Branch_01", 3, 2076],
    ["Flow_Branch_02", 3, 2077],
    ["Flow_Branch_03", 3, 2078],
    ["Flow_Branch_04", 3, 2079],
    ["Flow_Branch_05", 3, 2080],
    ["Flow_Branch_06", 3, 2081],
    ["Flow_Branch_07", 3, 2082],
    ["Flow_Branch_08", 3, 2083],
    ["Flow_Branch_09", 3, 2084],
    ["Flow_Branch_10", 3, 2085],
    ["Flow_Branch_11", 3, 2086],
    ["Flow_Branch_12", 3, 2087],
    ["Flow_Branch_13", 3, 2088],
    ["Flow_Branch_14", 3, 2089],
    ["Flow_Branch_15", 3, 2090],
    ["Level_Tank_01", 3, 2091],
    ["Level_Tank_02", 3, 2092],
    ["Level_Tank_03", 3, 2093],
    ["Level_Tank_04", 3, 2094],
    ["Level_Tank_05", 3, 2095],
    ["Level_Tank_06", 3, 2096],
    ["Level_Tank_07", 3, 2097],
    ["Level_Tank_08", 3, 2098],
    ["Level_Tank_09", 3, 2099],
    ["Level_Tank_10", 3, 2100],
    ["Level_Tank_11", 3, 2101],
    ["Level_Tank_12", 3, 2102],
    ["Level_Tank_13", 3, 2103],
    ["Level_Tank_14", 3, 2104],
    ["Level_Tank_15", 3, 2105],
    ["Level_Tank_16", 3, 2106],
    ["Level_Tank_17", 3, 2107],
    ["Level_Tank_18", 3, 2108],
    ["Level_Tank_19", 3, 2109],
    ["Level_Tank_20", 3, 2110],
    ["Vibration_Pump_01", 3, 2111],
    ["Vibration_Pump_02", 3, 2112],
    ["Vibration_Pump_03", 3, 2113],
    ["Vibration_Pump_04", 3, 2114],
    ["Vibration_Pump_05", 3, 2115],
    ["Vibration_Pump_06", 3, 2116],
    ["Vibration_Pump_07", 3, 2117],
    ["Vibration_Pump_08", 3, 2118],
    ["Vibration_Pump_09", 3, 2119],
    ["Vibration_Pump_10", 3, 2120],
    ["Vibration_Pump_11", 3, 2121],
    ["Vibration_Pump_12", 3, 2122],
    ["Vibration_Pump_13", 3, 2123],
    ["Vibration_Pump_14", 3, 2124],
    ["Vibration_Pump_15", 3, 2125],
    ["Vibration_Pump_16", 3, 2126],
    ["Vibration_Pump_17", 3, 2127],
    ["Vibration_Pump_18", 3, 2128],
    ["Vibration_Pump_19", 3, 2129],
    ["Vibration_Pump_20", 3, 2130],
    ["Power_Motor_01", 3, 2131],
    ["Power_Motor_02", 3, 2132],
    ["Power_Motor_03", 3, 2133],
    ["Power_Motor_04", 3, 2134],
    ["Power_Motor_05", 3, 2135],
    ["Power_Motor_06", 3, 2136],
    ["Power_Motor_07", 3, 2137],
    ["Power_Motor_08", 3, 2138],
    ["Power_Motor_09", 3, 2139],
    ["Power_Motor_10", 3, 2140],
    ["Power_Motor_11", 3, 2141],
    ["Power_Motor_12", 3, 2142],
    ["Power_Motor_13", 3, 2143],
    ["Power_Motor_14", 3, 2144],
    ["Power_Motor_15", 3, 2145],
    ["Power_Motor_16", 3, 2146],
    ["Power_Motor_17", 3, 2147],
    ["Power_Motor_18", 3, 2148],
    ["Power_Motor_19", 3, 2149],
    ["Power_Motor_20", 3, 2150],
    ["RPM_Motor_01", 3, 2151],
    ["RPM_Motor_02", 3, 2152],
    ["RPM_Motor_03", 3, 2153],
    ["RPM_Motor_04", 3, 2154],
    ["RPM_Motor_05", 3, 2155],
    ["RPM_Motor_06", 3, 2156],
    ["RPM_Motor_07", 3, 2157],
    ["RPM_Motor_08", 3, 2158],
    ["RPM_Motor_09", 3, 2159],
    ["RPM_Motor_10", 3, 2160],
    ["RPM_Motor_11", 3, 2161],
    ["RPM_Motor_12", 3, 2162],
    ["RPM_Motor_13", 3, 2163],
    ["RPM_Motor_14", 3, 2164],
    ["RPM_Motor_15", 3, 2165],
    ["RPM_Motor_16", 3, 2166],
    ["RPM_Motor_17", 3, 2167],
    ["RPM_Motor_18", 3, 2168],
    ["RPM_Motor_19", 3, 2169],
    ["RPM_Motor_20", 3, 2170],
    ["Humidity_Room_01", 3, 2171],
    ["Humidity_Room_02", 3, 2172],
    ["Humidity_Room_03", 3, 2173],
    ["Humidity_Room_04", 3, 2174],
    ["Humidity_Room_05", 3, 2175],
    ["Humidity_Room_06", 3, 2176],
    ["Humidity_Room_07", 3, 2177],
    ["Humidity_Room_08", 3, 2178],
    ["Humidity_Room_09", 3, 2179],
    ["Humidity_Room_10", 3, 2180],
    ["Current_Drive_01", 3, 2181],
    ["Current_Drive_02", 3, 2182],
    ["Current_Drive_03", 3, 2183],
    ["Current_Drive_04", 3, 2184],
    ["Current_Drive_05", 3, 2185],
    ["Current_Drive_06", 3, 2186],
    ["Current_Drive_07", 3, 2187],
    ["Current_Drive_08", 3, 2188],
    ["Current_Drive_09", 3, 2189],
    ["Current_Drive_10", 3, 2190],
    ["Current_Drive_11", 3, 2191],
    ["Current_Drive_12", 3, 2192],
    ["Current_Drive_13", 3, 2193],
    ["Current_Drive_14", 3, 2194],
    ["Current_Drive_15", 3, 2195],
    ["Current_Drive_16", 3, 2196],
    ["Current_Drive_17", 3, 2197],
    ["Current_Drive_18", 3, 2198],
    ["Current_Drive_19", 3, 2199],
    ["Current_Drive_20", 3, 2200],
    ["Voltage_Bus_01", 3, 2201],
    ["Voltage_Bus_02", 3, 2202],
    ["Voltage_Bus_03", 3, 2203],
    ["Voltage_Bus_04", 3, 2204],
    ["Voltage_Bus_05", 3, 2205],
    ["Voltage_Bus_06", 3, 2206],
    ["Voltage_Bus_07", 3, 2207],
    ["Voltage_Bus_08", 3, 2208],
    ["Voltage_Bus_09", 3, 2209],
    ["Voltage_Bus_10", 3, 2210],
    ["CO2_Zone_01", 3, 2211],
    ["CO2_Zone_02", 3, 2212],
    ["CO2_Zone_03", 3, 2213],
    ["CO2_Zone_04", 3, 2214],
    ["CO2_Zone_05", 3, 2215],
    ["CO2_Zone_06", 3, 2216],
    ["CO2_Zone_07", 3, 2217],
    ["CO2_Zone_08", 3, 2218],
    ["CO2_Zone_09", 3, 2219],
    ["CO2_Zone_10", 3, 2220],
    ["Noise_Floor_01", 3, 2221],
    ["Noise_Floor_02", 3, 2222],
    ["Noise_Floor_03", 3, 2223],
    ["Noise_Floor_04", 3, 2224],
    ["Noise_Floor_05", 3, 2225],
    ["Noise_Floor_06", 3, 2226],
    ["Noise_Floor_07", 3, 2227],
    ["Noise_Floor_08", 3, 2228],
    ["Noise_Floor_09", 3, 2229],
    ["Noise_Floor_10", 3, 2230],
    ["Torque_Motor_01", 3, 2231],
    ["Torque_Motor_02", 3, 2232],
    ["Torque_Motor_03", 3, 2233],
    ["Torque_Motor_04", 3, 2234],
    ["Torque_Motor_05", 3, 2235],
    ["Torque_Motor_06", 3, 2236],
    ["Torque_Motor_07", 3, 2237],
    ["Torque_Motor_08", 3, 2238],
    ["Torque_Motor_09", 3, 2239],
    ["Torque_Motor_10", 3, 2240],
    ["Torque_Motor_11", 3, 2241],
    ["Torque_Motor_12", 3, 2242],
    ["Torque_Motor_13", 3, 2243],
    ["Torque_Motor_14", 3, 2244],
    ["Torque_Motor_15", 3, 2245],
    ["Torque_Motor_16", 3, 2246],
    ["Torque_Motor_17", 3, 2247],
    ["Torque_Motor_18", 3, 2248],
    ["Torque_Motor_19", 3, 2249],
    ["Torque_Motor_20", 3, 2250],
    ["Temp_Ambient_01", 3, 2251],
    ["Temp_Ambient_02", 3, 2252],
    ["Temp_Ambient_03", 3, 2253],
    ["Temp_Ambient_04", 3, 2254],
    ["Temp_Ambient_05", 3, 2255],
    ["Temp_Ambient_06", 3, 2256],
    ["Temp_Ambient_07", 3, 2257],
    ["Temp_Ambient_08", 3, 2258],
    ["Temp_Ambient_09", 3, 2259],
    ["Temp_Ambient_10", 3, 2260],
    ["Flow_Coolant_01", 3, 2261],
    ["Flow_Coolant_02", 3, 2262],
    ["Flow_Coolant_03", 3, 2263],
    ["Flow_Coolant_04", 3, 2264],
    ["Flow_Coolant_05", 3, 2265],
    ["Flow_Coolant_06", 3, 2266],
    ["Flow_Coolant_07", 3, 2267],
    ["Flow_Coolant_08", 3, 2268],
    ["Flow_Coolant_09", 3, 2269],
    ["Flow_Coolant_10", 3, 2270],
    ["Press_Hydraulic_01", 3, 2271],
    ["Press_Hydraulic_02", 3, 2272],
    ["Press_Hydraulic_03", 3, 2273],
    ["Press_Hydraulic_04", 3, 2274],
    ["Press_Hydraulic_05", 3, 2275],
    ["Press_Hydraulic_06", 3, 2276],
    ["Press_Hydraulic_07", 3, 2277],
    ["Press_Hydraulic_08", 3, 2278],
    ["Press_Hydraulic_09", 3, 2279],
    ["Press_Hydraulic_10", 3, 2280],
    ["Temp_Oil_01", 3, 2281],
    ["Temp_Oil_02", 3, 2282],
    ["Temp_Oil_03", 3, 2283],
    ["Temp_Oil_04", 3, 2284],
    ["Temp_Oil_05", 3, 2285],
    ["Temp_Oil_06", 3, 2286],
    ["Temp_Oil_07", 3, 2287],
    ["Temp_Oil_08", 3, 2288],
    ["Temp_Oil_09", 3, 2289],
    ["Temp_Oil_10", 3, 2290],
    ["Temp_Cooling_01", 3, 2291],
    ["Temp_Cooling_02", 3, 2292],
    ["Temp_Cooling_03", 3, 2293],
    ["Temp_Cooling_04", 3, 2294],
    ["Temp_Cooling_05", 3, 2295],
    ["Temp_Cooling_06", 3, 2296],
    ["Temp_Cooling_07", 3, 2297],
    ["Temp_Cooling_08", 3, 2298],
    ["Temp_Cooling_09", 3, 2299],
    ["Temp_Cooling_10", 3, 2300]
]

@groovy.transform.Field static OpcUaClient opcClient = null
@groovy.transform.Field static List<String>  nodeNames = null
@groovy.transform.Field static List<NodeId>  nodeIds   = null
@groovy.transform.Field static final Object  LOCK = new Object()

def ensureConnected() {
    synchronized (LOCK) {
        if (nodeIds == null) {
            nodeNames = NODE_DEFS.collect { it[0] }
            nodeIds   = NODE_DEFS.collect { new NodeId(it[1] as int, it[2] as int) }
            log.info("[OPC] Built ${nodeIds.size()} NodeIds")
        }
        if (opcClient == null) {
            log.info("[OPC] Connecting to ${OPC_ENDPOINT} (discovery + SecurityPolicy.None filter)")
            // Use 3-arg create: does discovery, rewrites hostname in URL, filters for None security
            opcClient = OpcUaClient.create(
                OPC_ENDPOINT,
                { eps ->
                    log.info("[OPC] Discovered ${eps.size()} endpoints: ${eps*.securityPolicyUri}")
                    def ep = eps.find { it.securityPolicyUri == SecurityPolicy.None.uri }
                    log.info("[OPC] Selected endpoint: ${ep?.endpointUrl} policy=${ep?.securityPolicyUri}")
                    Optional.ofNullable(ep)
                } as java.util.function.Function,
                { OpcUaClientConfigBuilder b ->
                    b.setApplicationName(LocalizedText.english("NiFi OPC Client"))
                     .setApplicationUri("urn:nifi:opc:client:mintpower")
                     .setRequestTimeout(org.eclipse.milo.opcua.stack.core.types.builtin.unsigned.UInteger.valueOf(5000))
                     .build()
                } as java.util.function.Function
            )
            opcClient.connect().get(15, java.util.concurrent.TimeUnit.SECONDS)
            log.info("[OPC] Connected ✓  (${nodeIds.size()} nodes)")
        }
    }
}

try {
    ensureConnected()
    def values = opcClient.readValues(0.0, TimestampsToReturn.Both, nodeIds).get(15, java.util.concurrent.TimeUnit.SECONDS)
    def tags = [:]
    nodeNames.eachWithIndex { name, i ->
        def dv = values[i]
        tags[name] = dv?.statusCode?.isGood() ? dv.getValue()?.getValue() : null
    }
    def badCount = tags.values().count { it == null }
    def payload = [
        timestamp : java.time.Instant.now().toString(),
        source_id : SOURCE_ID,
        device_id : DEVICE_ID,
        tag_count : tags.size(),
        bad_count : badCount
    ] + tags
    def ff = session.create()
    ff = session.write(ff, { out -> out.write(JsonOutput.toJson(payload).getBytes("UTF-8")) } as OutputStreamCallback)
    ff = session.putAttribute(ff, "mime.type",  "application/json")
    ff = session.putAttribute(ff, "opc.source", SOURCE_ID)
    ff = session.putAttribute(ff, "tag.count",  "${tags.size()}")
    session.transfer(ff, REL_SUCCESS)
} catch (Exception e) {
    log.error("[OPC] Read failed: ${e.message}", e)
    synchronized (LOCK) { opcClient = null }
    def ff = session.create()
    ff = session.putAttribute(ff, "error.message", e.message ?: "unknown")
    ff = session.putAttribute(ff, "error.class",   e.class.simpleName)
    session.transfer(ff, REL_FAILURE)
}