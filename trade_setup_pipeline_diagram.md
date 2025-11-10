flowchart TD
    %% Pipeline Levels
    subgraph "Level 0: Candidates Only"
        L0[Level 0<br/>Candidates Only<br/>No Trades]
        L0_OR[Stage 1: Opening Range<br/>Establish Reference Level]
        L0_BRK[Stage 2: Breakout<br/>5m Candle Breaks OR]
        L0_RET[Stage 3: Retest<br/>1m Candle Retests Level]
    end

    subgraph "Level 1: Base Trading"
        L1[Level 1<br/>Base Criteria<br/>Execute Trades]
        L1_OR[Stage 1: Opening Range<br/>Establish Reference Level]
        L1_BRK[Stage 2: Breakout<br/>5m Candle Breaks OR]
        L1_RET[Stage 3: Retest<br/>1m Candle Retests Level]
        L1_ENTRY[Entry<br/>Open of 1m Candle<br/>After Retest]
    end

    subgraph "Level 2: Quality Filter"
        L2[Level 2<br/>Quality Filter<br/>All Components ≥ C]
        L2_OR[Stage 1: Opening Range<br/>Establish Reference Level]
        L2_BRK[Stage 2: Breakout<br/>5m Candle Breaks OR]
        L2_RET[Stage 3: Retest<br/>1m Candle Retests Level]
        L2_IGN[Stage 4: Ignition<br/>Post-Entry Confirmation]
        L2_FILTER[Quality Filter<br/>Breakout C+<br/>Retest C+<br/>Continuation C+<br/>R/R C+<br/>Context C+<br/>Rejects D Components]
        L2_ENTRY[Entry<br/>Open of 1m Candle<br/>After Retest/Ignition]
    end

    subgraph "Level 3: Elite Filter"
        L3[Level 3<br/>Elite Filter<br/>All Components C+<br/>Overall B+ 60+ pts]
        L3_OR[Stage 1: Opening Range<br/>Establish Reference Level]
        L3_BRK[Stage 2: Breakout<br/>5m Candle Breaks OR]
        L3_RET[Stage 3: Retest<br/>1m Candle Retests Level]
        L3_IGN[Stage 4: Ignition<br/>Post-Entry Confirmation]
        L3_FILTER[Elite Filter<br/>Breakout C+<br/>Retest C+<br/>Continuation C+<br/>R/R C+<br/>Context C+<br/>Overall 60+ pts<br/>Grade B+]
        L3_ENTRY[Entry<br/>Open of 1m Candle<br/>After Retest/Ignition]
    end

    %% Grading System
    subgraph "Grading System 100-Point Scale"
        GRADES[Component Grades<br/>Good A/B<br/>Warning B/C<br/>Fail D]
        OVERALL[Overall Grades<br/>A+: 4/4 Perfect<br/>A: 3/4 Perfect<br/>B: 2/4 Perfect<br/>C: <2 Perfect or Has Fails]
        COMPONENTS[Components<br/>Breakout 30 pts<br/>Retest 30 pts<br/>Continuation 20 pts<br/>R/R Ratio 10 pts<br/>Market Context 10 pts]
    end

    %% Flow Connections
    L0 --> L0_OR
    L0_OR --> L0_BRK
    L0_BRK --> L0_RET

    L1 --> L1_OR
    L1_OR --> L1_BRK
    L1_BRK --> L1_RET
    L1_RET --> L1_ENTRY

    L2 --> L2_OR
    L2_OR --> L2_BRK
    L2_BRK --> L2_RET
    L2_RET --> L2_IGN
    L2_IGN --> L2_FILTER
    L2_FILTER --> L2_ENTRY

    L3 --> L3_OR
    L3_OR --> L3_BRK
    L3_BRK --> L3_RET
    L3_RET --> L3_IGN
    L3_IGN --> L3_FILTER
    L3_FILTER --> L3_ENTRY

    %% Level Progression
    L0 -.-> L1 -.-> L2 -.-> L3

    %% Grading Connections
    GRADES --> COMPONENTS
    COMPONENTS --> OVERALL
    OVERALL --> L2_FILTER
    OVERALL --> L3_FILTER

    %% Styling
    classDef level0Class fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef level1Class fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef level2Class fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef level3Class fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef gradeClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px

    class L0,L0_OR,L0_BRK,L0_RET level0Class
    class L1,L1_OR,L1_BRK,L1_RET,L1_ENTRY level1Class
    class L2,L2_OR,L2_BRK,L2_RET,L2_IGN,L2_FILTER,L2_ENTRY level2Class
    class L3,L3_OR,L3_BRK,L3_RET,L3_IGN,L3_FILTER,L3_ENTRY level3Class
    class GRADES,OVERALL,COMPONENTS gradeClass
