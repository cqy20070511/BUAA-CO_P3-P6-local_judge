import java.util.*;
import java.util.prefs.*;
/** No registry reads/writes; all Logisim preferences are process-local. */
public final class MemoryPreferencesFactory implements PreferencesFactory {
    static final Preferences ROOT=new Node(null,"");
    public Preferences userRoot(){return ROOT;}
    public Preferences systemRoot(){return ROOT;}
    static final class Node extends AbstractPreferences {
        final Map<String,String> values=new HashMap<>();final Map<String,Node> children=new HashMap<>();
        Node(Node p,String n){super(p,n);}
        protected void putSpi(String k,String v){values.put(k,v);}
        protected String getSpi(String k){return values.get(k);}
        protected void removeSpi(String k){values.remove(k);}
        protected void removeNodeSpi(){}
        protected String[] keysSpi(){return values.keySet().toArray(new String[0]);}
        protected String[] childrenNamesSpi(){return children.keySet().toArray(new String[0]);}
        protected AbstractPreferences childSpi(String n){if(!children.containsKey(n))children.put(n,new Node(this,n));return children.get(n);}
        protected void syncSpi(){}protected void flushSpi(){}
    }
}
