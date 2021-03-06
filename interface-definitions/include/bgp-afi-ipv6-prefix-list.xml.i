<!-- included start from bgp-afi-ipv6-prefix-list.xml.i -->
<node name="prefix-list">
  <properties>
    <help>Prefix-list to filter route updates to/from this peer</help>
  </properties>
  <children>
    <leafNode name="export">
      <properties>
        <help>Prefix-list to filter outgoing route updates to this peer</help>
        <completionHelp>
          <path>policy prefix-list6</path>
        </completionHelp>
      </properties>
    </leafNode>
    <leafNode name="import">
      <properties>
        <help>Prefix-list to filter incoming route updates from this peer</help>
        <completionHelp>
          <path>policy prefix-list6</path>
        </completionHelp>
      </properties>
    </leafNode>
  </children>
</node>
<!-- included end -->
