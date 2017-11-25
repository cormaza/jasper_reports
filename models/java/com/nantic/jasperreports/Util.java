package com.nantic.jasperreports;
import net.sf.jasperreports.engine.JRAbstractScriptlet;
import net.sf.jasperreports.engine.JRDefaultScriptlet;
import net.sf.jasperreports.engine.JRScriptletException;
import java.util.*;

public class Util extends JRDefaultScriptlet{

    public Integer[] getIds(String[] lista) throws JRScriptletException{
        Integer[] res = new Integer[lista.length];
        for (int i = 0; i < lista.length; i++) {
            try {
                res[i] = Integer.parseInt(lista[i]);
            } catch (Exception e) {
            }
        }
        return res;
    }
    
    public String addAsterisk(String originalString, int count) throws JRScriptletException{
    	String newString = originalString;
    	int length = count - originalString.length();
    	if (length > 0){
    		for (int i = 0; i < length; i++){
        		newString = newString + " *";
    		}
    	}
    	return newString;
    }

    public String addSpaces(String originalString, int count) throws JRScriptletException{
    	String newString = originalString;
		for (int i = 1; i < count; i++){
    		newString = "  " + newString;
		}
    	return newString;
    }
}
