package com.expedition.afrique;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(AfricaMediaPlugin.class);   // notre plugin photos+GPS
        super.onCreate(savedInstanceState);
    }
}
